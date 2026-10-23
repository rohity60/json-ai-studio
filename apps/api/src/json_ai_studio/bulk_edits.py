"""Server-side expansion of LLM bulk edit operations.

For changes that hit many elements ("apply to all 701 records", "first 100
shloks") the model cannot list every diff: when the document is too large
to inline it only sees a skeleton (one sample element per array), and even
when it sees everything, hundreds of diffs blow the output token budget.

Instead the model emits a compact pattern in the response's ``bulk`` list::

    {"path": "/records/*/sectionId",
     "where": {"slokNumber": {"gte": 1, "lte": 100}},
     "operation": "modify", "new_value": "abc"}

and the server expands it against the FULL working JSON into ordinary
DiffEntry dicts (with real ``old_value``s), which then flow through the
normal apply / accept / reject / history path unchanged.

Pattern rules:
- ``path`` is a JSON Pointer where ``*`` matches every array element or
  object key at that level.
- ``where`` (optional) is evaluated against the node matched by the LAST
  ``*``. Keys are field names or relative pointers ("a/b"); ``$value`` is
  the target value itself; ``$index`` is the array index (or key) matched by
  the last ``*``. A plain value means equality; an object uses operators
  eq, ne, in, nin, gt, gte, lt, lte, contains (case-insensitive substring),
  exists.
- ``operation``: modify (set), add (set only where the key is missing),
  delete (remove the matched node).
- ``new_value`` may be ``{"$from": "<field>"}`` to copy, per element, the
  value of another field of the element matched by the last ``*`` (e.g.
  "set modifiedDate to its creationDate"). Elements lacking that field are
  skipped. Without this the model used to write a placeholder string into
  every element.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Iterator

from .diff_utils import _split_path

_FENCE_PREFIXES = ("```json", "```")


class BulkEditError(ValueError):
    """A bulk op is malformed (bad path / operator / operation)."""


# -- Parsing -----------------------------------------------------------------


def answer_object(text: str | None) -> dict[str, Any] | None:
    """The model's top-level answer object from raw output, or None.

    Tolerates code fences and prose around the JSON, like
    ``parse_llm_response``. Shared by bulk ops and clarifying questions.
    """
    raw = (text or "").strip()
    for prefix in _FENCE_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :].rstrip("`").strip()
            break
    decoder = json.JSONDecoder()
    start = raw.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(raw[start:])
        except ValueError:
            start = raw.find("{", start + 1)
            continue
        return value if isinstance(value, dict) else None
    return None


def extract_bulk(text: str | None) -> tuple[list[dict[str, Any]], str]:
    """Pull the ``bulk`` list (and explanation) out of raw LLM output.

    Returns ([], "") when the output has no bulk ops.
    """
    value = answer_object(text)
    if value is not None and isinstance(value.get("bulk"), list):
        ops = [op for op in value["bulk"] if isinstance(op, dict)]
        explanation = value.get("explanation")
        return ops, str(explanation) if explanation else ""
    return [], ""


def extract_question(text: str | None) -> dict[str, Any] | None:
    """Clarifying question from the answer: {"text", "options"} or None.

    Options are trimmed to 4 short strings; a question without options is
    allowed (the user answers in free text).
    """
    value = answer_object(text)
    q = value.get("question") if value is not None else None
    if not isinstance(q, dict):
        return None
    question = str(q.get("text", "")).strip()
    if not question:
        return None
    options = [
        str(o).strip()[:80]
        for o in (q.get("options") or [])
        if isinstance(o, (str, int, float)) and str(o).strip()
    ][:4]
    return {"text": question[:300], "options": options}


# -- Matching ----------------------------------------------------------------


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _children(node: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(node, list):
        for i, child in enumerate(node):
            yield str(i), child
    elif isinstance(node, dict):
        yield from ((str(k), v) for k, v in node.items())


def _step(node: Any, part: str) -> tuple[bool, Any]:
    if isinstance(node, list):
        if part.isdigit() and int(part) < len(node):
            return True, node[int(part)]
        return False, None
    if isinstance(node, dict) and part in node:
        return True, node[part]
    return False, None


def _walk(
    node: Any, parts: list[str], walked: list[str], anchor: tuple | None
) -> Iterator[tuple[list[str], bool, Any, tuple | None]]:
    """Yield (concrete_parts, exists, value, anchor) for every match.

    ``anchor`` = (node, key) captured at the last ``*``, for ``where``.
    The final segment may be missing (``exists`` False) so ``add`` can
    create a field on each matched element.
    """
    if not parts:
        yield walked, True, node, anchor
        return
    head, rest = parts[0], parts[1:]
    if head == "*":
        for key, child in _children(node):
            yield from _walk(child, rest, walked + [key], (child, key))
        return
    found, child = _step(node, head)
    if found:
        yield from _walk(child, rest, walked + [head], anchor)
    elif not rest and isinstance(node, dict):
        yield walked + [head], False, None, anchor


_MISSING = object()


def _resolve(node: Any, key: str) -> Any:
    current = node
    for part in [p for p in key.strip("/").split("/") if p]:
        found, current = _step(current, part.replace("~1", "/").replace("~0", "~"))
        if not found:
            return _MISSING
    return current


def _norm(value: Any) -> Any:
    return value.casefold() if isinstance(value, str) else value


# Spellings small models emit for the canonical operators.
_OPERATOR_ALIASES = {
    "neq": "ne",
    "!=": "ne",
    "not_eq": "ne",
    "not_equal": "ne",
    "==": "eq",
    "equals": "eq",
    "equal": "eq",
    ">": "gt",
    ">=": "gte",
    "ge": "gte",
    "<": "lt",
    "<=": "lte",
    "le": "lte",
    "not_in": "nin",
    "includes": "contains",
}


def _container(value: Any) -> bool:
    return isinstance(value, (dict, list))


def _check(actual: Any, cond: Any) -> bool:
    if not isinstance(cond, dict):
        return actual is not _MISSING and _norm(actual) == _norm(cond)
    for raw_op, expected in cond.items():
        op = _OPERATOR_ALIASES.get(str(raw_op).strip().lower(), raw_op)
        if op == "exists":
            if (actual is not _MISSING) != bool(expected):
                return False
            continue
        if actual is _MISSING:
            return False
        try:
            if op == "eq":
                ok = _norm(actual) == _norm(expected)
            elif op == "ne":
                ok = _norm(actual) != _norm(expected)
            elif op == "in":
                ok = _norm(actual) in [_norm(e) for e in expected]
            elif op == "nin":
                ok = _norm(actual) not in [_norm(e) for e in expected]
            elif op == "gt":
                ok = actual > expected
            elif op == "gte":
                ok = actual >= expected
            elif op == "lt":
                ok = actual < expected
            elif op == "lte":
                ok = actual <= expected
            elif op == "contains":
                hay = (
                    json.dumps(actual, ensure_ascii=False)
                    if not isinstance(actual, str)
                    else actual
                )
                ok = str(expected).casefold() in hay.casefold()
            else:
                raise BulkEditError(f"unknown operator {op!r}")
        except TypeError:  # e.g. "abc" > 5
            ok = False
        if not ok:
            return False
    return True


def _matches(where: dict[str, Any], anchor: tuple | None, value: Any) -> bool:
    node, key = anchor if anchor else (None, None)
    for field, cond in where.items():
        if field == "$value":
            actual = value
        elif field == "$index":
            actual = int(key) if isinstance(key, str) and key.isdigit() else key
        else:
            actual = _resolve(node, field) if anchor else _MISSING
        if not _check(actual, cond):
            return False
    return True


# -- Expansion ---------------------------------------------------------------


def expand_bulk(op: dict[str, Any], doc: Any, max_matches: int) -> list[dict[str, Any]]:
    """Expand one bulk op into concrete diffs against ``doc``.

    Raises BulkEditError on a malformed op or when matches exceed
    ``max_matches`` (guards against accidental whole-document rewrites).
    """
    path = op.get("path")
    if not isinstance(path, str) or "*" not in path:
        raise BulkEditError("bulk path must be a JSON Pointer containing '*'")
    operation = str(op.get("operation", "modify")).strip().lower()
    operation = {"set": "modify", "update": "modify", "remove": "delete"}.get(
        operation, operation
    )
    if operation not in ("modify", "add", "delete"):
        raise BulkEditError(f"unsupported bulk operation {operation!r}")
    where = op.get("where") or {}
    if not isinstance(where, dict):
        raise BulkEditError("bulk 'where' must be an object")

    parts = _split_path(path)
    diffs: list[dict[str, Any]] = []
    for concrete, exists, value, anchor in _walk(doc, parts, [], None):
        if operation != "add" and not exists:
            continue
        if operation == "add" and exists:
            continue
        if where and not _matches(where, anchor, value if exists else _MISSING):
            continue
        new_value = None if operation == "delete" else op.get("new_value")
        copied = isinstance(new_value, dict) and set(new_value) == {"$from"}
        if copied:
            if not anchor:
                raise BulkEditError("'$from' needs a '*' element to copy from")
            new_value = _resolve(anchor[0], str(new_value["$from"]))
            if new_value is _MISSING:
                continue  # this element has no source field
            new_value = copy.deepcopy(new_value)
        if operation == "modify" and value == new_value:
            continue  # already has the target value
        if (
            operation == "modify"
            and not copied  # $from copies the element's own data verbatim
            and _container(value) != _container(new_value)
        ):
            # e.g. writing 60 over a whole parameters array — almost always a
            # pattern one level too shallow; never destroy structure in bulk.
            raise BulkEditError(
                "would replace a "
                + (
                    "list/object with a single value"
                    if _container(value)
                    else "single value with a list/object"
                )
                + f" at {'/' + '/'.join(concrete)}; target the elements (add '/*') instead"
            )
        diffs.append(
            {
                "path": "/" + "/".join(_escape(p) for p in concrete),
                "operation": operation,
                "old_value": value if exists else None,
                "new_value": new_value,
            }
        )
        if len(diffs) > max_matches:
            raise BulkEditError(
                f"bulk edit matched more than {max_matches} locations; narrow it"
            )
    return diffs


def expand_all(
    ops: list[dict[str, Any]], doc: Any, max_matches: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Expand every op. Returns (diffs, notes) — notes describe each op's
    match count or error, for the user-facing explanation."""
    diffs: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[str] = set()
    for op in ops:
        try:
            expanded = expand_bulk(op, doc, max_matches)
        except BulkEditError as exc:
            notes.append(f"Bulk edit on {op.get('path')!r} not applied: {exc}.")
            continue
        fresh = [d for d in expanded if d["path"] not in seen]
        seen.update(d["path"] for d in fresh)
        diffs.extend(fresh)
        if not expanded:
            notes.append(f"Bulk edit on {op.get('path')} matched nothing.")
        else:
            notes.append(f"Bulk edit matched {len(expanded)} location(s).")
    return diffs, notes
