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
import difflib
import json
import logging
import re
from typing import Any

from .preview import ends_with_preview_marker

logger = logging.getLogger("json_ai_studio.diff_utils")


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


# ---------------------------------------------------------------------------
# Truncation guard (edit-safety ES-01..07)
# ---------------------------------------------------------------------------

TRUNCATION_REASON = "truncated preview copied — read the full value first"
_GUARD_MIN_OLD_CHARS = 120  # shorter than the skeleton's str_cap + slack
_FUZZY_MAX_OLD_CHARS = 50_000  # fuzzy tail search above this is too slow
_GUARD_SHRINK = 0.85  # only values that lost > 15 % are checked
_TAIL_CHARS = 160  # how much of the new value's ending is located in the old
_TAIL_MATCH = 0.6  # SequenceMatcher ratio that counts as "same passage"
_TAIL_STEP = 40


def _current_value(doc: Any, parts: list[str]) -> tuple[bool, Any]:
    """(exists, value) at parts, without mutating or raising."""
    current = doc
    for part in parts:
        if isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                return False, None
            current = current[int(part)]
        elif isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
        else:
            return False, None
    return True, current


def _tail_end_in_old(old: str, new: str) -> int | None:
    """Where in `old` the passage that `new` ends with stops, or None.

    Slides a window over `old` and keeps the best fuzzy match for the last
    _TAIL_CHARS of `new` (typo fixes / punctuation changes still match).
    """
    tail = new[-_TAIL_CHARS:].rstrip(" .…)]}\"'")
    if len(tail) < 20:
        return None
    # Unedited ending: cheap exact probes, any size (the last few chars may
    # be the model's own, so the start of the tail is probed too).
    for probe, after in ((tail[-60:], 0), (tail[:60], len(tail) - 60)):
        at = old.find(probe) if len(probe) == 60 else -1
        if at >= 0:
            return at + 60 + max(0, after)
    if len(old) > _FUZZY_MAX_OLD_CHARS:
        return None
    width = len(tail) + _TAIL_STEP  # equal-length windows: fair ratios
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(tail)
    best_ratio, best_end = 0.0, None
    last = max(0, len(old) - width)
    starts = list(range(0, last, _TAIL_STEP)) + [last]
    for start in starts:  # ties keep the earliest (safer: reject)
        window = old[start : start + width]
        matcher.set_seq1(window)
        if matcher.real_quick_ratio() < _TAIL_MATCH:
            continue
        if matcher.quick_ratio() < _TAIL_MATCH:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_ratio, best_end = ratio, start + len(window)
    return best_end if best_ratio >= _TAIL_MATCH else None


def _looks_like_copied_preview(old: str, new: str) -> bool:
    """True when `new` is a cut-down (and maybe edited) copy of `old`.

    - `new` ends with a preview marker and is shorter than `old` (ES-01/04);
    - or `new` is clearly shorter and its ending is a passage from the
      *middle* of `old`: the model rewrote what it saw of a truncated
      preview / tool read and dropped the rest (repros 2026-11-10:
      7485 → 80 chars, 7485 → 3392 chars with typo fixes and "...)" ending).
      A full rewrite or summary ends like `old` ends, or matches nowhere.

    Deliberately cutting a long text in half is refused too: losing data
    silently is worse than one failed diff the user can redo explicitly.
    """
    if len(new) >= len(old):
        return False
    if ends_with_preview_marker(new):
        return True
    if len(old) < _GUARD_MIN_OLD_CHARS:
        return False
    if len(new) > len(old) * _GUARD_SHRINK:
        return False
    end = _tail_end_in_old(old, new)
    return end is not None and end < len(old) - max(_TAIL_CHARS, len(old) * 0.15)


def _find_copied_preview(old: Any, new: Any) -> bool:
    if isinstance(new, str):
        return isinstance(old, str) and _looks_like_copied_preview(old, new)
    if isinstance(new, dict) and isinstance(old, dict):
        return any(k in old and _find_copied_preview(old[k], v) for k, v in new.items())
    if isinstance(new, list) and isinstance(old, list):
        return any(_find_copied_preview(o, n) for o, n in zip(old, new))
    return False


def check_truncation(diff: dict[str, Any], doc: Any) -> None:
    """Refuse a modify/add whose new_value is a copied (cut-down) preview.

    In skeleton/tool modes the model sees long strings cut at a marker; a
    diff built from that preview would silently shrink the field (repro
    2026-11-10: 7485 → 80 chars). Raises DiffApplyError(TRUNCATION_REASON).
    """
    try:
        op = _resolve_op(diff)
        parts = _split_path(diff.get("path", ""))
    except DiffApplyError:
        return  # _apply_one reports these
    if op == "delete" or not parts:
        return
    exists, old = _current_value(doc, parts)
    if not exists:
        return
    new = diff.get("new_value")
    if _find_copied_preview(old, new):
        logger.info(
            "edit guard rejected path=%s old_len=%d new_len=%d",
            diff.get("path"),
            len(json.dumps(old, ensure_ascii=False, default=str)),
            len(json.dumps(new, ensure_ascii=False, default=str)),
        )
        raise DiffApplyError(TRUNCATION_REASON)


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
    """Reorder same-list index ops (delete/modify/add) so higher indices
    go first.

    LLMs compute every index against one snapshot of the document.
    Applying a lower index first (e.g. a delete at 1) shifts every
    higher index that follows (e.g. a modify at 3) out from under it,
    even though the model's indices were internally consistent.
    Processing a list's indexed ops highest-index-first avoids this:
    deleting/inserting at index k only shifts elements originally at
    index > k, so by the time a lower index is handled, nothing above
    it that could move it has been touched yet. Only ops sharing the
    same list parent are reordered, and only among the positions they
    already occupy (unaffected diffs elsewhere keep their relative
    order).
    """
    groups: dict[tuple[str, ...], list[int]] = {}
    for i, diff in enumerate(diffs):
        try:
            parts = _split_path(diff.get("path", ""))
            op = _resolve_op(diff)
        except DiffApplyError:
            continue
        if op in ("delete", "modify", "add") and parts and parts[-1].isdigit():
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
                check_truncation(diff, result)
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
    raw_op = str(entry.get("operation", "")).strip().lower()
    op = _OP_ALIASES.get(raw_op)
    from .text_edits import TEXT_OPS, normalize_text_edit  # circular at import

    if op is None and raw_op not in TEXT_OPS:
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
    if op is None:
        # In-string find/replace; expanded to a modify diff server-side.
        return normalize_text_edit(entry, path)
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
