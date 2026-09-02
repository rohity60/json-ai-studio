"""Diff mutation utilities + LLM diff-response parsing.

Applies or reverts DiffEntry dicts (path / operation / old_value /
new_value) on a JSON document. Paths are JSON Pointers (RFC 6901):
segments separated by "/", with "~1" unescaping to "/" and "~0" to "~".
Numeric segments index lists only when the parent is actually a list,
so dicts with numeric string keys stay addressable.

Strictness contract: navigation never auto-creates parents and never
falls back to a different location. Any diff whose path does not
resolve raises DiffApplyError instead of silently mutating the wrong
node. Callers decide whether to skip (apply_all_verbose) or surface
the error (single accept/reject endpoints).
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


class DiffApplyError(ValueError):
    """Raised when a diff cannot be applied or reverted at its path."""


# LLM output uses several synonyms for the three canonical operations.
_OP_ALIASES: dict[str, str] = {
    "add": "add",
    "insert": "add",
    "append": "add",
    "modify": "modify",
    "replace": "modify",
    "update": "modify",
    "set": "modify",
    "change": "modify",
    "delete": "delete",
    "remove": "delete",
    "del": "delete",
}


def _unescape(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


def _split_path(path: Any) -> list[str]:
    if not isinstance(path, str):
        raise DiffApplyError(f"diff path must be a string, got {type(path).__name__}")
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        path = "/" + path
    return [_unescape(p) for p in path.split("/")[1:] if p != ""]


def _list_index(part: str, length: int, *, allow_end: bool) -> int:
    """Resolve a path segment to a list index. '-' means append (add only)."""
    if part == "-":
        if allow_end:
            return length
        raise DiffApplyError("index '-' is only valid for 'add' operations")
    if not part.isdigit():
        raise DiffApplyError(f"invalid list index {part!r}")
    idx = int(part)
    limit = length + 1 if allow_end else length
    if idx >= limit:
        raise DiffApplyError(f"list index {idx} out of range (length {length})")
    return idx


def _navigate(doc: Any, parts: list[str]) -> tuple[Any, str]:
    """Walk to the parent of the target. Raises DiffApplyError on any miss."""
    current = doc
    walked: list[str] = []
    for part in parts[:-1]:
        walked.append(part)
        location = "/" + "/".join(walked)
        if isinstance(current, list):
            idx = _list_index(part, len(current), allow_end=False)
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                raise DiffApplyError(f"path {location!r} does not exist")
            current = current[part]
        else:
            raise DiffApplyError(
                f"cannot descend into non-container value at {location!r}"
            )
    return current, parts[-1]


def _resolve_op(diff: dict[str, Any]) -> str:
    op = _OP_ALIASES.get(str(diff.get("operation", "")).strip().lower())
    if op is None:
        raise DiffApplyError(f"unknown operation {diff.get('operation')!r}")
    return op


def _apply_one(diff: dict[str, Any], doc: Any) -> None:
    """Apply a single diff to doc in place. Raises DiffApplyError on failure."""
    parts = _split_path(diff.get("path", ""))
    if not parts:
        return  # whole-document diffs are treated as no-ops
    parent, key = _navigate(doc, parts)
    op = _resolve_op(diff)
    path = diff.get("path")

    if op == "delete":
        if isinstance(parent, list):
            parent.pop(_list_index(key, len(parent), allow_end=False))
        elif isinstance(parent, dict):
            if key not in parent:
                raise DiffApplyError(f"cannot delete missing key at {path!r}")
            del parent[key]
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")
    elif op == "add":
        if isinstance(parent, list):
            parent.insert(
                _list_index(key, len(parent), allow_end=True), diff.get("new_value")
            )
        elif isinstance(parent, dict):
            parent[key] = diff.get("new_value")
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")
    else:  # modify
        if isinstance(parent, list):
            parent[_list_index(key, len(parent), allow_end=False)] = diff.get(
                "new_value"
            )
        elif isinstance(parent, dict):
            # Upsert: LLMs frequently say "modify" when adding a new key.
            parent[key] = diff.get("new_value")
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")


def _revert_one(diff: dict[str, Any], doc: Any) -> None:
    """Undo a single diff on doc in place. Raises DiffApplyError on failure."""
    parts = _split_path(diff.get("path", ""))
    if not parts:
        return
    parent, key = _navigate(doc, parts)
    op = _resolve_op(diff)
    path = diff.get("path")

    if op == "add":
        if isinstance(parent, list):
            length = len(parent)
            if key == "-":
                if length == 0:
                    raise DiffApplyError(f"cannot revert add on empty list {path!r}")
                parent.pop()
            else:
                parent.pop(_list_index(key, length, allow_end=False))
        elif isinstance(parent, dict):
            if key not in parent:
                raise DiffApplyError(f"cannot revert add of missing key {path!r}")
            del parent[key]
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")
    elif op == "modify":
        old_value = diff.get("old_value")
        if isinstance(parent, list):
            parent[_list_index(key, len(parent), allow_end=False)] = old_value
        elif isinstance(parent, dict):
            parent[key] = old_value
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")
    else:  # delete -> re-insert the removed value
        old_value = diff.get("old_value")
        if isinstance(parent, list):
            idx = _list_index(key, len(parent), allow_end=True)
            parent.insert(idx, old_value)
        elif isinstance(parent, dict):
            parent[key] = old_value
        else:
            raise DiffApplyError(f"parent of {path!r} is not a container")


def _order_for_apply(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reorder deletes that target the same list so higher indices go first.

    LLMs compute all indices against the original document; deleting
    index 1 before index 3 would shift the second target. Only delete
    entries sharing the same list parent are reordered, and only among
    the positions they already occupy.
    """
    groups: dict[tuple[str, ...], list[int]] = {}
    for i, diff in enumerate(diffs):
        try:
            parts = _split_path(diff.get("path", ""))
            op = _resolve_op(diff)
        except DiffApplyError:
            continue
        if op == "delete" and parts and parts[-1].isdigit():
            groups.setdefault(tuple(parts[:-1]), []).append(i)

    result = list(diffs)
    for positions in groups.values():
        if len(positions) < 2:
            continue
        reordered = sorted(
            (diffs[i] for i in positions),
            key=lambda d: int(_split_path(d["path"])[-1]),
            reverse=True,
        )
        for pos, diff in zip(positions, reordered):
            result[pos] = diff
    return result


class DiffUtils:
    """Apply or revert DiffEntry dicts on a JSON document.

    All methods deep-copy the input document and return the mutated
    copy; the original is never modified.
    """

    @staticmethod
    def apply(diff: dict[str, Any], json_doc: dict[str, Any]) -> dict[str, Any]:
        """Apply one diff. Returns a new document; raises DiffApplyError."""
        result = copy.deepcopy(json_doc)
        _apply_one(diff, result)
        return result

    @staticmethod
    def revert(diff: dict[str, Any], json_doc: dict[str, Any]) -> dict[str, Any]:
        """Undo one diff. Returns a new document; raises DiffApplyError."""
        result = copy.deepcopy(json_doc)
        _revert_one(diff, result)
        return result

    @staticmethod
    def apply_all(
        diffs: list[dict[str, Any]], json_doc: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a list of diffs, skipping any that fail. Returns new copy."""
        result, _, _ = DiffUtils.apply_all_verbose(diffs, json_doc)
        return result

    @staticmethod
    def apply_all_verbose(
        diffs: list[dict[str, Any]], json_doc: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
        """Apply a list of diffs; report what applied and what failed.

        Returns (result, applied, failed) where failed is a list of
        (diff, reason) pairs. Failed diffs never mutate the document.
        """
        result = copy.deepcopy(json_doc)
        applied: list[dict[str, Any]] = []
        failed: list[tuple[dict[str, Any], str]] = []
        for diff in _order_for_apply(list(diffs)):
            try:
                _apply_one(diff, result)
                applied.append(diff)
            except DiffApplyError as exc:
                failed.append((diff, str(exc)))
        return result, applied, failed


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```[\w-]*[ \t]*\r?\n(.*?)\r?\n?```\s*$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([\]}])")
# Empty/leading array elements from small models: "[ , {...}]", "[, x]",
# "[a,,b]". Observed leaking valid sibling diffs at users when the outer
# array failed to parse and only one inner object could be salvaged.
_EMPTY_ELEM_RE = re.compile(r"([\[,])\s*,")
# Pull the model's "explanation" string even when the surrounding JSON is
# malformed, so a partial/garbled response never leaks raw JSON at the user.
_EXPLANATION_RE = re.compile(r'"explanation"\s*:\s*"((?:\\.|[^"\\])*)"')


def _repair_json(s: str) -> str:
    """Best-effort fixes for common small-model JSON defects, applied only
    as a fallback parse candidate: trailing commas ({"a":1,} / [1,2,]),
    and leading/empty/doubled array elements ([ , {...}] / [a,,b])."""
    prev = None
    out = s
    while out != prev:  # collapse runs like [,,,] in one pass each
        prev = out
        out = _EMPTY_ELEM_RE.sub(r"\1", out)
    return _TRAILING_COMMA_RE.sub(r"\1", out)


def normalize_entry(d: Any) -> dict[str, Any] | None:
    """Coerce one LLM-emitted dict into a canonical DiffEntry, or None."""
    if not isinstance(d, dict):
        return None
    entry = dict(d)
    if "operation" not in entry and "op" in entry:
        entry["operation"] = entry["op"]
    op = _OP_ALIASES.get(str(entry.get("operation", "")).strip().lower())
    if op is None:
        return None
    path = entry.get("path")
    if not isinstance(path, str) or not path.strip():
        key = entry.get("key")
        if key is None:
            return None
        path = "/" + str(key).replace(".", "/")
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    new_value = entry.get("new_value", entry.get("value"))
    return {
        "path": path,
        "operation": op,
        "old_value": entry.get("old_value"),
        "new_value": new_value,
    }


def _coerce_diffs(value: Any) -> tuple[list[dict[str, Any]], str] | None:
    """Interpret a parsed JSON value as diff output. None = not diff-shaped."""
    if isinstance(value, list):
        entries = [e for e in (normalize_entry(d) for d in value) if e is not None]
        if entries or all(isinstance(d, dict) for d in value):
            return entries, ""
        return None
    if isinstance(value, dict):
        if isinstance(value.get("diffs"), list):
            entries = [
                e for e in (normalize_entry(d) for d in value["diffs"]) if e is not None
            ]
            explanation = value.get("explanation")
            return entries, str(explanation) if explanation else ""
        single = normalize_entry(value)
        if single is not None:
            return [single], ""
        return None
    return None


def _extract_explanation(text: str) -> str:
    """Pull the model's "explanation" string out of a (possibly malformed)
    response, so a garbled diff payload never leaks raw JSON as the message."""
    m = _EXPLANATION_RE.search(text)
    if not m:
        return ""
    try:
        return json.loads('"' + m.group(1) + '"')  # unescape via JSON
    except ValueError:
        return m.group(1)


def _salvage_entries(text: str, decoder: "json.JSONDecoder") -> list[dict[str, Any]]:
    """Collect every substring that decodes to a valid diff entry, skipping
    malformed siblings. Runs only after a whole-object parse failed, so the
    diffs the model got right still apply. Advancing past each decoded object
    avoids re-scanning its internals (e.g. an object-valued new_value)."""
    entries: list[dict[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        try:
            value, end = decoder.raw_decode(text[i:])
        except ValueError:
            i += 1
            continue
        entry = normalize_entry(value) if isinstance(value, dict) else None
        if entry is not None:
            entries.append(entry)
            i += end
        else:
            i += 1
    return entries


def parse_llm_response(text: str | None) -> tuple[list[dict[str, Any]], str]:
    """Parse raw LLM output into (diffs, explanation).

    Handles: a bare JSON array of entries, a {"diffs": [...],
    "explanation": "..."} object, a single entry object, markdown code
    fences (with or without a language tag), and prose before/after the
    JSON (kept as the explanation). Returns ([], text) when no diff
    JSON is found so callers can show the text to the user.
    """
    raw = (text or "").strip()
    if not raw:
        return [], ""
    fence = _FENCE_RE.match(raw)
    body = fence.group(1).strip() if fence else raw

    decoder = json.JSONDecoder()
    candidates = [body]
    # Also try a copy with common small-model JSON defects repaired (trailing
    # commas, leading/empty/doubled array elements).
    repaired = _repair_json(body)
    if repaired != body:
        candidates.append(repaired)

    def _try(candidate: str, start: int) -> tuple[list[dict[str, Any]], str] | None:
        try:
            value, end = decoder.raw_decode(candidate[start:])
        except ValueError:
            return None
        coerced = _coerce_diffs(value)
        if coerced is None:
            return None
        diffs, explanation = coerced
        surrounding = (candidate[:start] + " " + candidate[start + end :]).strip()
        return diffs, explanation or surrounding

    # Pass 1: decode each candidate as a whole from its first bracket. This
    # prefers the complete {"diffs":[...]} object over salvaging a single
    # embedded element — the latter used to drop sibling diffs and leak the
    # rest as the explanation when the outer array was malformed.
    for candidate in candidates:
        first = next((i for i, ch in enumerate(candidate) if ch in "[{"), None)
        if first is not None and (result := _try(candidate, first)) is not None:
            return result

    # Pass 2: salvage. A whole-object parse failed (the model emitted broken
    # JSON — e.g. a doubled key `"path": "x": "y"`, or truncation). Collect
    # every diff entry that still decodes on its own, and pull the model's
    # explanation separately. This keeps the valid changes AND guarantees the
    # user never sees raw JSON as the "explanation".
    salvaged = _salvage_entries(body, decoder)
    explanation = _extract_explanation(body)
    if salvaged:
        return salvaged, explanation
    if explanation:
        return [], explanation

    # Nothing usable. Never surface raw model JSON — a friendly, actionable
    # message when it looked like a diff payload; genuine prose passes through.
    stripped = body.lstrip()
    if stripped.startswith(("{", "[")) or '"diffs"' in body:
        return [], (
            "I couldn't apply that cleanly — the change I generated was too "
            "large or malformed to parse. Try narrowing the request to "
            "specific fields, or splitting it into smaller steps."
        )
    return [], body
