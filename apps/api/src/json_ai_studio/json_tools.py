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
import re
from typing import Any

from .bulk_edits import BulkEditError, _MISSING, _matches, _walk, normalize_where
from .bulk_edits import _resolve as _field
from .diff_utils import DiffApplyError, _split_path
from .preview import ELLIPSIS, TRUNCATED_SUFFIX

_PREVIEW_CHARS = 160
_CONTEXT_CHARS = 800
_MAX_LIMIT = 50
_MAX_CONTEXT_LEVELS = 3
_MAX_BATCH_PATHS = 500  # paths one batch read may name (ranges expanded)
_OUTLINE_MIN_CHARS = 200  # shorter strings are not worth listing
_RANGE = re.compile(r"^(.*)/(\d+)\.\.(\d*)$")  # /entries/4..13, /entries/4..
_NUMERIC_OPS = ("gt", "gte", "lt", "lte")


class ToolError(ValueError):
    """Bad tool arguments — returned to the model as data, never raised."""


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _compact(value: Any, chars: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    return text if len(text) <= chars else text[:chars] + ELLIPSIS


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
- read(path, offset?): the exact value at a JSON Pointer ("" = root). No wildcards — use query for those. A long STRING comes back in pages ("text", "length", "next_offset"): read again with offset=next_offset until you have seen the part you need (all of it, for a full proofread).
- read(paths) or read(path "/entries/4..13"): SEVERAL values in one call — a list of pointers, or an index range of an array ("4.." = to the end). Returns as many as this AI model's limits allow ("results"); when "next_paths" is present, read those next. Never read array elements one call at a time.
- outline(path?, top?): the largest strings and arrays under a path with their sizes — no values. Use it first when asked to review, proofread or fix "everything", to see where the content is.
T0. Tool calls come BEFORE your final answer and are not "output": the "EXACTLY ONE JSON object" rule applies only to your final reply. If answering needs any value, element or reference not visible in the SKELETON, your first response MUST be a tool call — do not describe a plan to search, actually call search/read.
T0b. search = free text inside ONE value; query = conditions on fields of the same element. Never put "field: value" pairs into search.
T0c. search finds LITERAL text that is in the document. Never search for words describing the task ("errors", "typos", "censorship", a language name, the user's sentence) — for reviews use outline, then read.
T0d. When the user names a part ("entries 40 to 50", "the next 20 from 38"), read exactly that range (path "/entries/40..50") and nothing else. Indexes are 0-based as in the paths; if the user counts from 1, say which indexes you used.
T0e. If a read result says the turn has no room for more, stop reading: answer for what you read and state which range was covered and where to continue.
T1. Never guess a value you cannot see: search for it, read it, and use the exact path and old_value the tools return.
T2. Follow references (an index or id that points elsewhere, e.g. into /Imports or /Exports) by reading the target, not by assuming.
T2b. To change words or sentences inside a long string, use "replace_text" diffs (TEXT EDITS) with "find" copied exactly from the "text" you read — never rewrite the whole string from a partial read.
T3. Several targets matching one rule → prefer a single "bulk" op once you know the field and filter.
T4. Tools only read. When done, reply with the usual single JSON object. Analysis requests may end with no diffs and a longer "explanation" citing the paths you found."""

    def __init__(
        self,
        doc: Any,
        result_max_chars: int = 4000,
        batch_max_chars: int | None = None,
    ) -> None:
        self.doc = doc
        self.result_max_chars = result_max_chars
        # Hard cap for one batch read; the room actually available is set
        # per round from the deployment budget (set_batch_room).
        self.batch_max_chars = max(
            result_max_chars, batch_max_chars or result_max_chars * 3
        )
        self.batch_room = min(self.batch_max_chars, result_max_chars * 3)
        self.reads_end = False  # no further read can follow this round
        self.last_result: dict[str, Any] | None = None

    def set_batch_room(self, chars: int | None, last_round: bool = False) -> None:
        """Characters batch reads may return in the coming round. `chars`
        comes from the deployment's token budget and context window (None =
        no known limit → 3 single results). Never below one single result,
        never above the hard cap."""
        # After this round nothing more can be read in this turn: either
        # the model must answer next, or the room left is already down to a
        # single result. Batch reads then say "stop and report" instead of
        # "read the rest".
        self.reads_end = last_round or (
            chars is not None and chars < self.result_max_chars * 2
        )
        if chars is None:
            chars = self.result_max_chars * 3
        self.batch_room = max(
            self.result_max_chars, min(int(chars), self.batch_max_chars)
        )

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
        where = normalize_where(where)
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
        out: dict[str, Any] = {
            "path": path,
            "where": where,
            "total": total,
            "matches": matches,
            "truncated": total > len(matches),
        }
        if total == 0 and where:
            hint = self._where_hint(path, where)
            if hint:
                out["hint"] = hint
        return out

    def _where_hint(self, path: str, where: dict[str, Any]) -> str | None:
        """Why nothing matched: a number comparison on a text field."""
        for field, cond in where.items():
            if field.startswith("$") or not isinstance(cond, dict):
                continue
            if not any(
                op in _NUMERIC_OPS and isinstance(v, (int, float))
                for op, v in cond.items()
            ):
                continue
            seen = 0
            sample = None
            for _, exists, _, anchor in _walk(self.doc, _parts(path), [], None):
                if not exists or not anchor:
                    continue
                actual = _field(anchor[0], field)
                if actual is _MISSING:
                    continue
                if not isinstance(actual, str):
                    sample = None
                    break
                sample = actual if sample is None else sample
                seen += 1
                if seen >= 50:
                    break
            if sample is not None:
                return (
                    f'"{field}" is a text field here (e.g. '
                    f"{_compact(sample, 60)}), so number comparisons never match "
                    'it. For positions in the array use "$index".'
                )
        return None

    def read(self, args: dict[str, Any]) -> dict[str, Any]:
        paths = self._batch_paths(args)
        if paths is not None:
            return self._read_many(paths)
        path = str(args.get("path", "") or "")
        value = _resolve(self.doc, _parts(path))
        text = json.dumps(value, ensure_ascii=False, default=str)
        budget = self.result_max_chars - 200
        out: dict[str, Any] = {"path": path, "type": _type(value)}
        if isinstance(value, str) and (
            len(text) > budget or args.get("offset") not in (None, 0, "0")
        ):
            return self._read_text(path, value, args, budget - 300)
        if len(text) <= budget:
            out["value"] = value
        else:
            out["value_truncated"] = text[:budget] + ELLIPSIS
            out["hint"] = (
                "too large to return whole: read a deeper path, or search within it (path_prefix)"
            )
        return out

    def _batch_paths(self, args: dict[str, Any]) -> list[str] | None:
        """Paths of a batch read (`paths` list and/or index ranges), or None
        for an ordinary single read."""
        given = args.get("paths")
        if given is None:
            path = str(args.get("path", "") or "")
            if not _RANGE.match(path):
                return None
            given = [path]
        elif isinstance(given, str):
            given = [given]
        if not isinstance(given, list) or not given:
            raise ToolError("paths must be a non-empty list of JSON Pointers")
        out: list[str] = []
        for raw in given:
            raw = str(raw)
            m = _RANGE.match(raw)
            if not m:
                out.append(raw)
            else:
                base, start = m.group(1), int(m.group(2))
                items = _resolve(self.doc, _parts(base))
                if not isinstance(items, list):
                    raise ToolError(f"{base or '/'}: index ranges need an array")
                if start >= len(items):
                    raise ToolError(f"{base}: array has only {len(items)} items")
                end = min(int(m.group(3)), len(items) - 1) if m.group(3) else None
                end = len(items) - 1 if end is None else end
                out.extend(f"{base}/{i}" for i in range(start, end + 1))
            if len(out) > _MAX_BATCH_PATHS:
                raise ToolError(
                    f"too many paths (max {_MAX_BATCH_PATHS} per call); "
                    "read a smaller range"
                )
        return out

    def _read_many(self, paths: list[str]) -> dict[str, Any]:
        """As many of `paths`, in order, as fit the batch room — the number
        depends on each value's real size and on the deployment's limits."""
        room = self.batch_room - 400  # envelope: counts, next_paths, hint
        results: list[dict[str, Any]] = []
        used = 0
        done = 0
        for path in paths:
            try:
                entry: dict[str, Any] = {
                    "path": path,
                    "value": _resolve(self.doc, _parts(path)),
                }
            except ToolError as exc:
                entry = {"path": path, "error": str(exc)}
            size = len(json.dumps(entry, ensure_ascii=False, default=str)) + 1
            if used + size > room:
                if results:
                    break
                # Even one value is too large: page / truncate it as a
                # single read would.
                entry = self.read({"path": path})
                size = len(json.dumps(entry, ensure_ascii=False, default=str))
            results.append(entry)
            used += size
            done += 1
            if used >= room:
                break
        out: dict[str, Any] = {
            "results": results,
            "returned": done,
            "requested": len(paths),
        }
        rest = paths[done:]
        if rest:
            out["remaining"] = len(rest)
            if self.reads_end:
                # The turn has no room for more: a model told to "read the
                # rest" keeps trying and is cut off without saying how far
                # it got.
                out["covered"] = {"first": paths[0], "last": paths[done - 1]}
                out["continue_from"] = rest[0]
                out["hint"] = (
                    f"Only {done} of {len(paths)} values fit and this turn has "
                    "no room for more. Do NOT read again. Answer now for what "
                    "you have read, and state in the explanation exactly what "
                    f"was covered ({paths[0]} to {paths[done - 1]}) and that "
                    f"{len(rest)} remain, starting at {rest[0]} — the user can "
                    "ask to continue from there."
                )
            else:
                out["next_paths"] = rest[:20]
                out["hint"] = (
                    f"{done} of {len(paths)} values fit this AI model's limit "
                    "for one call; read the rest with paths=next_paths."
                )
        # Calls of the same round share the room.
        self.batch_room = max(self.result_max_chars, self.batch_room - used)
        return out

    def outline(self, args: dict[str, Any]) -> dict[str, Any]:
        """Where the content is: largest strings and arrays, sizes only."""
        prefix = _parts(str(args.get("path", "") or ""))
        root = _resolve(self.doc, prefix)
        top = _int(args.get("top"), 20, 1, _MAX_LIMIT)
        rows: list[dict[str, Any]] = []

        def size(node: Any, parts: list[str]) -> int:
            if isinstance(node, str):
                if len(node) >= _OUTLINE_MIN_CHARS:
                    rows.append(
                        {"path": _pointer(parts), "type": "str", "chars": len(node)}
                    )
                return len(node) + 2
            if isinstance(node, list):
                n = 2 + sum(size(v, parts + [str(i)]) + 1 for i, v in enumerate(node))
                row = {
                    "path": _pointer(parts),
                    "type": "list",
                    "items": len(node),
                    "chars": n,
                }
                if node:
                    row["avg_item_chars"] = n // len(node)
                rows.append(row)
                return n
            if isinstance(node, dict):
                return 2 + sum(
                    len(str(k)) + 4 + size(v, parts + [str(k)]) for k, v in node.items()
                )
            return len(json.dumps(node, default=str))

        total = size(root, prefix)
        rows.sort(key=lambda r: r["chars"], reverse=True)
        return {
            "path": _pointer(prefix),
            "total_chars": total,
            "top": rows[:top],
            "truncated": len(rows) > top,
        }

    @staticmethod
    def _read_text(
        path: str, value: str, args: dict[str, Any], budget: int
    ) -> dict[str, Any]:
        """One page of a long string: raw text from `offset`, sized so its
        JSON-escaped form fits the result cap. Pages are exact substrings,
        so any snippet in them can be used as a replace_text "find"."""
        offset = _int(args.get("offset"), 0, 0, len(value))
        chunk = value[offset : offset + budget]
        while chunk and len(json.dumps(chunk, ensure_ascii=False)) > budget:
            chunk = chunk[: int(len(chunk) * 0.85)]  # escapes (\n, \") grow
        if offset + len(chunk) < len(value):
            # End on whitespace: a page cut mid-word ("…scaled with In") reads
            # as a typo, and the model "fixed" it (prod 2026-11-12).
            cut = max(chunk.rfind(" "), chunk.rfind("\n"), chunk.rfind("\t"))
            if cut > len(chunk) // 2:
                chunk = chunk[: cut + 1]
        end = offset + len(chunk)
        out: dict[str, Any] = {
            "path": path,
            "type": "str",
            "length": len(value),
            "offset": offset,
            "text": chunk,
        }
        if end < len(value):
            out["next_offset"] = end
            out["hint"] = (
                f"string continues: read again with offset={end} for the next "
                "part. To fix text inside it, use a replace_text diff."
            )
        return out

    # -- dispatch ----------------------------------------------------------

    def call(self, name: str, raw_args: str | dict[str, Any] | None) -> str:
        """Run a tool; always returns a JSON string (errors as data)."""
        handlers = {
            "search": self.search,
            "query": self.query,
            "read": self.read,
            "outline": self.outline,
        }
        room = self.batch_room  # before a batch read spends it
        try:
            if name not in handlers:
                raise ToolError(
                    f"unknown tool {name!r}; available: search, query, read, outline"
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
        # Structured result for progress messages (counts, truncation).
        self.last_result = result if isinstance(result, dict) else None
        text = json.dumps(result, ensure_ascii=False, default=str)
        batch = isinstance(result, dict) and "results" in result
        cap = room if batch else self.result_max_chars
        if len(text) > cap:
            text = text[:cap] + TRUNCATED_SUFFIX
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
                    "description": "Return the exact value at a JSON Pointer path (e.g. /records/22 or /Imports/4). Long strings come back in pages (text, length, next_offset); other very large values are truncated. Several values in one call: give paths, or an index range such as /entries/4..13 — as many as fit the model's limits are returned, the rest is listed in next_paths.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": 'JSON Pointer; "" is the whole document.',
                            },
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Several JSON Pointers (or index ranges like /entries/4..13) to read in one call, instead of path.",
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Long strings only: character offset to read from (use next_offset from the previous page).",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "outline",
                    "description": "Sizes only, no values: the largest strings and arrays under a path, biggest first. Use before reviewing or proofreading a whole document to see where the content is.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": 'JSON Pointer to look under; "" (default) is the whole document.',
                            },
                            "top": {
                                "type": "integer",
                                "description": "How many entries (default 20, max 50).",
                            },
                        },
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
