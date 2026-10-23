"""Read-only lookup tools for large documents (ADR-0024).

Documents too large to inline reach the model as a key-union skeleton: every
key, but sample values only. To edit or analyse values it cannot see, the
model scans that key tree, then calls:

- ``search``  find keys or scalar values containing text (case-insensitive),
              optionally with the enclosing object(s) as context
- ``query``   elements matching field conditions — the bulk-edit syntax
              (``/records/*`` + ``where``), e.g. several fields at once, or a
              reverse reference lookup (``StackNode == -2``)
- ``read``    the exact value at a JSON Pointer — full values whose previews
              were cut, and reference hops (e.g. an index into /Imports)

Both are pure reads over the session's working JSON. Edits still happen only
in the model's final answer (diffs / bulk) through the normal pipeline.
Results are size-capped so a tool call can never flood the context.
"""

from __future__ import annotations

import json
from typing import Any

from .bulk_edits import BulkEditError, _MISSING, _matches, _walk
from .diff_utils import DiffApplyError, _split_path

_PREVIEW_CHARS = 160
_CONTEXT_CHARS = 800
_MAX_LIMIT = 50
_MAX_CONTEXT_LEVELS = 3


class ToolError(ValueError):
    """Bad tool arguments — returned to the model as data, never raised."""


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _compact(value: Any, chars: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= chars else text[:chars] + "…"


def _type(value: Any) -> str:
    if isinstance(value, dict):
        return f"object({len(value)} keys)"
    if isinstance(value, list):
        return f"array({len(value)} items)"
    return "null" if value is None else type(value).__name__


def _parts(path: str) -> list[str]:
    try:
        return _split_path(path or "")
    except DiffApplyError as exc:
        raise ToolError(str(exc)) from exc


def _pointer(parts: list[str]) -> str:
    return "".join(f"/{_esc(p)}" for p in parts)


def _resolve(doc: Any, parts: list[str]) -> Any:
    current = doc
    for i, part in enumerate(parts):
        here = _pointer(parts[: i + 1])
        if isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                raise ToolError(
                    f"{here}: no such index (array has {len(current)} items)"
                )
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                raise ToolError(f"{here}: no such key")
            current = current[part]
        else:
            raise ToolError(f"{here}: parent is a {_type(current)}, not a container")
    return current


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


class JsonToolbox:
    """search / read bound to one working document."""

    INSTRUCTIONS = """\
TOOLS — this document is too large to show in full. Scan the SKELETON above for keys, then use your read-only tools:
- search(query, scope?, path_prefix?, context_levels?, limit?): find scalar VALUES (scope "values", default) or KEY names (scope "keys") containing the text, case-insensitive. Returns JSON Pointer paths in document order, each value, and with context_levels=1..3 the enclosing object(s).
- query(path, where?, limit?): elements matching FIELD CONDITIONS, same syntax as "bulk" — path with "*" wildcards, "where" filters the element matched by the LAST "*" (field names / relative pointers, "$value", "$index"; plain value = equality; operators eq, ne, in, nin, gt, gte, lt, lte, contains, exists). Use it to match SEVERAL fields at once (e.g. path "/records/*", where {"slokNumber": 23, "sectionId": "bhagavad_gita_ch_3"}) and to find what REFERS to something (e.g. path "/Exports/*/ScriptBytecode/*", where {"StackNode": -2}).
- read(path): the exact value at a JSON Pointer ("" = root). No wildcards — use query for those.
T0. Tool calls come BEFORE your final answer and are not "output": the "EXACTLY ONE JSON object" rule applies only to your final reply. If answering needs any value, element or reference not visible in the SKELETON, your first response MUST be a tool call — do not describe a plan to search, actually call search/read.
T0b. search = free text inside ONE value; query = conditions on fields of the same element. Never put "field: value" pairs into search.
T1. Never guess a value you cannot see: search for it, read it, and use the exact path and old_value the tools return.
T2. Follow references (an index or id that points elsewhere, e.g. into /Imports or /Exports) by reading the target, not by assuming.
T3. Several targets matching one rule → prefer a single "bulk" op once you know the field and filter.
T4. Tools only read. When done, reply with the usual single JSON object. Analysis requests may end with no diffs and a longer "explanation" citing the paths you found."""

    def __init__(self, doc: Any, result_max_chars: int = 4000) -> None:
        self.doc = doc
        self.result_max_chars = result_max_chars

    # -- tools -------------------------------------------------------------

    def search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolError("query is required")
        scope = str(args.get("scope", "values")).lower()
        if scope not in ("values", "keys", "both"):
            raise ToolError("scope must be values, keys or both")
        limit = _int(args.get("limit"), 20, 1, _MAX_LIMIT)
        levels = _int(args.get("context_levels"), 0, 0, _MAX_CONTEXT_LEVELS)
        prefix = _parts(str(args.get("path_prefix", "") or ""))
        root = _resolve(self.doc, prefix)

        needle = query.casefold()
        matches: list[dict[str, Any]] = []
        total = 0
        # Pre-order walk: pop a node, test it, push its children reversed —
        # matches come out in document order without sorting.
        stack = list(reversed(_children(root, prefix)))
        while stack:
            parts, key, value, keyed = stack.pop()
            hit = scope in ("keys", "both") and keyed and needle in str(key).casefold()
            if not hit and scope in ("values", "both"):
                hit = (
                    not isinstance(value, (dict, list))
                    and value is not None
                    and needle in str(value).casefold()
                )
            if hit:
                total += 1
                if len(matches) < limit:
                    match = {
                        "path": _pointer(parts),
                        "value": _compact(value, _PREVIEW_CHARS),
                    }
                    if levels and len(parts) - len(prefix) >= 1:
                        up = parts[: max(len(prefix), len(parts) - levels)]
                        match["context"] = {
                            "path": _pointer(up),
                            "value": _compact(_resolve(self.doc, up), _CONTEXT_CHARS),
                        }
                    matches.append(match)
            if isinstance(value, (dict, list)):
                stack.extend(reversed(_children(value, parts)))
        return {
            "query": query,
            "total": total,
            "matches": matches,
            "truncated": total > len(matches),
        }

    def query(self, args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path", "") or "")
        if not path.startswith("/"):
            raise ToolError('path must be a JSON Pointer such as "/records/*"')
        where = args.get("where") or {}
        if not isinstance(where, dict):
            raise ToolError("where must be an object of field conditions")
        limit = _int(args.get("limit"), 20, 1, _MAX_LIMIT)
        matches: list[dict[str, Any]] = []
        total = 0
        try:
            for parts, exists, value, anchor in _walk(self.doc, _parts(path), [], None):
                if not exists:
                    continue
                if where and not _matches(where, anchor, value if exists else _MISSING):
                    continue
                total += 1
                if len(matches) < limit:
                    matches.append(
                        {
                            "path": _pointer(parts),
                            "value": _compact(value, _CONTEXT_CHARS),
                        }
                    )
        except BulkEditError as exc:
            raise ToolError(str(exc)) from exc
        return {
            "path": path,
            "where": where,
            "total": total,
            "matches": matches,
            "truncated": total > len(matches),
        }

    def read(self, args: dict[str, Any]) -> dict[str, Any]:
        path = str(args.get("path", "") or "")
        value = _resolve(self.doc, _parts(path))
        text = json.dumps(value, ensure_ascii=False, default=str)
        budget = self.result_max_chars - 200
        out: dict[str, Any] = {"path": path, "type": _type(value)}
        if len(text) <= budget:
            out["value"] = value
        else:
            out["value_truncated"] = text[:budget] + "…"
            out["hint"] = (
                "too large to return whole: read a deeper path, or search within it (path_prefix)"
            )
        return out

    # -- dispatch ----------------------------------------------------------

    def call(self, name: str, raw_args: str | dict[str, Any] | None) -> str:
        """Run a tool; always returns a JSON string (errors as data)."""
        handlers = {"search": self.search, "query": self.query, "read": self.read}
        try:
            if name not in handlers:
                raise ToolError(
                    f"unknown tool {name!r}; available: search, query, read"
                )
            if isinstance(raw_args, str):
                args = json.loads(raw_args) if raw_args.strip() else {}
            else:
                args = raw_args or {}
            if not isinstance(args, dict):
                raise ToolError("arguments must be a JSON object")
            result: Any = handlers[name](args)
        except (ToolError, ValueError) as exc:
            result = {"error": str(exc)}
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > self.result_max_chars:
            text = text[: self.result_max_chars] + "…(truncated)"
        return text

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        """OpenAI-style function schemas (LiteLLM translates per provider)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Find scalar values (or key names) in the CURRENT WORKING JSON containing text, case-insensitive. Returns JSON Pointer paths in document order with values, total count, and optionally the enclosing object(s).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Text to find."},
                            "scope": {
                                "type": "string",
                                "enum": ["values", "keys", "both"],
                                "description": "Search scalar values (default), key names, or both.",
                            },
                            "path_prefix": {
                                "type": "string",
                                "description": "Only search under this JSON Pointer, e.g. /Exports/12.",
                            },
                            "context_levels": {
                                "type": "integer",
                                "description": "0-3: also return the object this many levels above each match (default 0).",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max matches (default 20, max 50).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query",
                    "description": "Elements of the CURRENT WORKING JSON matching field conditions, using the bulk-edit syntax: path with * wildcards, where filters the element matched by the last *. Use for several fields at once and for finding what refers to an id/index.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "JSON Pointer with * wildcards, e.g. /records/* or /Exports/*/ScriptBytecode/*.",
                            },
                            "where": {
                                "type": "object",
                                "description": 'Field conditions, e.g. {"slokNumber": 23, "sectionId": "ch_3"} or {"StackNode": -2} or {"Value": {"gt": 4}}.',
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max matches (default 20, max 50).",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read",
                    "description": "Return the exact value at a JSON Pointer path (e.g. /records/22 or /Imports/4). Very large values are truncated.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": 'JSON Pointer; "" is the whole document.',
                            }
                        },
                        "required": ["path"],
                    },
                },
            },
        ]


def _children(node: Any, parts: list[str]) -> list[tuple[list[str], Any, Any, bool]]:
    if isinstance(node, list):
        return [(parts + [str(i)], i, v, False) for i, v in enumerate(node)]
    if isinstance(node, dict):
        return [(parts + [str(k)], k, v, True) for k, v in node.items()]
    return []
