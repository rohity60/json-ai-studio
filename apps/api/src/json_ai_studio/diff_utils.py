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


def _join_path(parts: list[str]) -> str:
    return "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts)


def _list_prefix_len(doc: Any, parts: list[str]) -> int | None:
    """Length of the path prefix up to and including the FIRST segment that
    indexes a list ('-' or digits under a list), or None if there is none."""
    current = doc
    for n, part in enumerate(parts):
        if isinstance(current, list):
            return n + 1 if (part == "-" or part.isdigit()) else None
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return None


def _normalise_append_runs(
    diffs: list[dict[str, Any]], doc: Any
) -> list[dict[str, Any]]:
    """Rewrite add runs numbered one-after-another into snapshot form.

    The prompt asks for snapshot indices (every index refers to the
    document as shown). Models often number several inserts
    sequentially instead (RFC 6902 style: 50, 51, 52, 53). That is only
    detectable when the run reaches past the end of the list — such an
    index is invalid in snapshot form. Then the run of consecutive adds
    on one list is one block inserted at its first index k, in model
    order. When k >= len - 1 the block is appended ('-'): an off-by-one
    count of a long list is far likelier than "insert before the last
    item" (prod 2026-11-21: 4 roles at 50..53 on a 51-item list).
    """
    runs: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    for i, d in enumerate(diffs):
        try:
            parts = _split_path(d.get("path", ""))
            op = _resolve_op(d)
        except DiffApplyError:
            continue
        if op != "add" or not parts or not parts[-1].isdigit():
            continue
        runs.setdefault(tuple(parts[:-1]), []).append((int(parts[-1]), i))

    out = list(diffs)
    for parent, items in runs.items():
        if len(items) < 2:
            continue
        exists, target = _current_value(doc, list(parent))
        if not exists or not isinstance(target, list):
            continue
        length = len(target)
        idxs = sorted(idx for idx, _ in items)
        if idxs[-1] <= length:
            continue  # every index valid in snapshot form: trust it
        if any(b != a + 1 for a, b in zip(idxs, idxs[1:])):
            continue  # not one block; leave invalid ones to fail
        start = idxs[0]
        seg = "-" if start >= length - 1 else str(start)
        new_path = _join_path([*parent, seg])
        logger.info(
            "normalise append_run parent=%s indices=%s..%s length=%d -> %s",
            _join_path(list(parent)),
            idxs[0],
            idxs[-1],
            length,
            new_path,
        )
        for _, i in items:
            out[i] = {**out[i], "path": new_path}
    return out


def _retarget_by_old_value(
    diffs: list[dict[str, Any]], doc: Any
) -> list[dict[str, Any]]:
    """Fix list indices of delete/modify diffs using their old_value.

    old_value names the element the model meant. When the value at the
    given index is not old_value but exactly ONE element of that list
    has old_value at the same relative path, the diff is pointed at that
    element. Catches deletes/modifies numbered one after another
    ("delete A at 0, then C at 1") and miscounted indices in long lists
    (live evals 2026-11-23, nvidia nemotron + gemma). No unique match →
    left as is. Also drops modifies whose new_value equals old_value
    (models restating elements they think shifted).
    """
    out: list[dict[str, Any]] = []
    for d in diffs:
        try:
            op = _resolve_op(d)
            parts = _split_path(d.get("path", ""))
        except DiffApplyError:
            out.append(d)
            continue
        old = d.get("old_value")
        if op == "modify" and "old_value" in d and old == d.get("new_value"):
            logger.info("normalise drop no-op modify path=%s", d.get("path"))
            continue
        if op == "modify" and old is not None and not isinstance(old, (dict, list)):
            # Path one level too high: modify /cards/2 old 'C' new 'C2'
            # where /cards/2 is {"name": "C", ...} (gemma4 2026-11-23).
            exists, current = _current_value(doc, parts)
            if (
                exists
                and isinstance(current, dict)
                and not isinstance(d.get("new_value"), (dict, list))
            ):
                keys = [k for k, v in current.items() if v == old]
                if len(keys) == 1:
                    new_path = _join_path([*parts, keys[0]])
                    logger.info(
                        "normalise deepen modify %s -> %s", d.get("path"), new_path
                    )
                    d = {**d, "path": new_path}
                    parts = [*parts, keys[0]]
        n = _list_prefix_len(doc, parts)
        if op not in ("delete", "modify") or old is None or n is None:
            out.append(d)
            continue
        exists, current = _current_value(doc, parts)
        if exists and current == old:
            out.append(d)
            continue
        head, tail = parts[: n - 1], parts[n:]
        _, items = _current_value(doc, head)
        matches = [
            j
            for j in range(len(items))
            if _current_value(doc, [*head, str(j), *tail]) == (True, old)
        ]
        if len(matches) != 1:
            out.append(d)
            continue
        new_path = _join_path([*head, str(matches[0]), *tail])
        logger.info(
            "normalise retarget by old_value op=%s %s -> %s",
            op,
            d.get("path"),
            new_path,
        )
        out.append({**d, "path": new_path})
    return out


def _star_add_to_append(diffs: list[dict[str, Any]], doc: Any) -> list[dict[str, Any]]:
    """An add at '/list/*' (bulk wildcard misused in a plain diff) means
    append (live eval: gemma4 sent 'add /roles/*' for 4 new roles)."""
    out = []
    for d in diffs:
        parts = _split_path(d.get("path", "")) if isinstance(d, dict) else []
        if (
            parts
            and parts[-1] == "*"
            and str(d.get("operation", "")).lower() in ("add", "insert", "append")
        ):
            exists, target = _current_value(doc, parts[:-1])
            if exists and isinstance(target, list):
                new_path = _join_path([*parts[:-1], "-"])
                logger.info("normalise star add %s -> %s", d.get("path"), new_path)
                d = {**d, "path": new_path}
        out.append(d)
    return out


def normalise_diffs(diffs: list[dict[str, Any]], doc: Any) -> list[dict[str, Any]]:
    """Server-side index repair before applying a model answer (snapshot
    convention, prompt rule 4). Order: '*' adds → '-', delete/modify
    retargeted by old_value, sequential append runs folded."""
    diffs = _star_add_to_append(list(diffs), doc)
    diffs = _retarget_by_old_value(diffs, doc)
    return _normalise_append_runs(diffs, doc)


_OP_RANK = {"delete": 0, "modify": 0, "add": 1}


def _apply_order(diffs: list[dict[str, Any]], doc: Any = None) -> list[int]:
    """Positions of diffs in the order that keeps snapshot indices valid.

    Contract (prompt rule 4): every index refers to the document as
    shown, before any of these diffs. Applying in DESCENDING document
    position keeps that true — an insert/delete at position k only
    shifts positions after k, which were already handled. Grouped by the
    outermost list a path goes through, so nested ops (/items/3/name)
    sort with their element. Within a group, compared segment by
    segment: higher index first; '-' (append) after every index, in
    model order; a deeper path before its ancestor (modify the element
    before inserting in front of / deleting it). Same path: delete and
    modify before add; several adds at one index in reverse model order
    so they end up in model order. Diffs outside list groups keep their
    positions and relative order.
    """
    if doc is None:
        doc = {}
    groups: dict[tuple[str, ...], list[int]] = {}
    split: dict[int, list[str]] = {}
    for i, diff in enumerate(diffs):
        try:
            parts = _split_path(diff.get("path", ""))
            _resolve_op(diff)
        except DiffApplyError:
            continue
        n = _list_prefix_len(doc, parts)
        if n is None and parts and (parts[-1].isdigit() or parts[-1] == "-"):
            n = len(parts)  # parent missing/not a list: still group by it
        if n is None:
            continue
        split[i] = parts[n - 1 :]
        groups.setdefault(tuple(parts[: n - 1]), []).append(i)

    def cmp(i: int, j: int) -> int:
        a, b = split[i], split[j]
        for sa, sb in zip(a, b):
            if sa == sb:
                continue
            if sa.isdigit() and sb.isdigit():
                return -1 if int(sa) > int(sb) else 1
            if sa == "-":
                return 1
            if sb == "-":
                return -1
            return i - j  # different dict keys: model order
        if len(a) != len(b):
            return -1 if len(a) > len(b) else 1  # deeper first
        ra = _OP_RANK.get(_resolve_op(diffs[i]), 0)
        rb = _OP_RANK.get(_resolve_op(diffs[j]), 0)
        if ra != rb:
            return ra - rb
        if ra == 1 and a[-1] != "-":
            return j - i  # adds at one index: reverse model order
        return i - j

    from functools import cmp_to_key

    result = list(range(len(diffs)))
    for positions in groups.values():
        if len(positions) < 2:
            continue
        ordered = sorted(positions, key=cmp_to_key(cmp))
        for pos, src in zip(positions, ordered):
            result[pos] = src
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
        Indices are snapshot indices (all against json_doc); see
        _apply_order. applied / failed are returned in the input
        (model) order, not apply order. A diff rewritten by
        normalise_diffs is returned with its rewritten path.

        Every applied diff also gets "preview_path": where it sits in the
        RESULT (later ops in the batch can shift it). Reject reverts with
        it. An append ("-") is stored with its concrete index as "path"
        (the "-" kept as "model_path" for accept on the baseline), so "-"
        never reaches history, the UI or reject.
        """
        result = copy.deepcopy(json_doc)
        normalised = normalise_diffs(diffs, json_doc)
        applied: list[tuple[int, dict[str, Any]]] = []
        failed: list[tuple[int, tuple[dict[str, Any], str]]] = []
        steps: list[tuple[str, list[str]]] = []  # (op, concrete parts)
        for n in _apply_order(normalised, json_doc):
            diff = normalised[n]
            try:
                check_truncation(diff, result)
                parts = _split_path(diff.get("path", ""))
                if parts and parts[-1] == "-":
                    _, parent = _current_value(result, parts[:-1])
                    if isinstance(parent, list):
                        parts = [*parts[:-1], str(len(parent))]
                _apply_one(diff, result)
                steps.append((_resolve_op(diff), parts))
                applied.append((n, diff))
            except DiffApplyError as exc:
                failed.append((n, (diff, str(exc))))

        final: list[tuple[int, dict[str, Any]]] = []
        for k, (n, diff) in enumerate(applied):
            parts = steps[k][1]
            for op, later in steps[k + 1 :]:
                parts = _shift_parts(parts, op, later, result)
            preview = _join_path(parts) if parts else diff.get("path", "")
            entry = {**diff, "preview_path": preview}
            if _split_path(diff.get("path", ""))[-1:] == ["-"]:
                entry["model_path"] = diff["path"]
                entry["path"] = preview
            final.append((n, entry))
        return (
            result,
            [d for _, d in sorted(final, key=lambda p: p[0])],
            [f for _, f in sorted(failed, key=lambda p: p[0])],
        )

    @staticmethod
    def accept_form(diff: dict[str, Any]) -> dict[str, Any]:
        """The diff as applied to the BASELINE on accept: an append keeps
        its "-" (the baseline may lack earlier pending items)."""
        if diff.get("model_path"):
            return {**diff, "path": diff["model_path"]}
        return diff

    @staticmethod
    def revert_checked(
        diff: dict[str, Any], json_doc: dict[str, Any]
    ) -> dict[str, Any]:
        """Undo one diff from the PREVIEW. Uses its preview_path, but first
        checks the element there is still the one this diff produced (an
        earlier reject may have shifted it): an add's element must equal
        new_value, a modify's value must equal new_value. If not, the ONE
        element of that list that matches is used; none or several →
        DiffApplyError (never removes the wrong element)."""
        target = {**diff, "path": diff.get("preview_path") or diff.get("path", "")}
        target["path"] = _locate_for_revert(target, json_doc)
        return DiffUtils.revert(target, json_doc)


def _shift_parts(parts: list[str], op: str, op_parts: list[str], doc: Any) -> list[str]:
    """Move a concrete path past a LATER list insert/delete (op_parts)."""
    depth = len(op_parts) - 1
    if op not in ("add", "delete") or depth < 0 or len(parts) <= depth:
        return parts
    if parts[:depth] != op_parts[:depth]:
        return parts
    seg, at = parts[depth], op_parts[depth]
    if not (seg.isdigit() and at.isdigit()):
        return parts
    exists, parent = _current_value(doc, op_parts[:depth])
    if not exists or not isinstance(parent, list):
        return parts
    i, j = int(seg), int(at)
    if op == "add" and j <= i:
        i += 1
    elif op == "delete" and j < i:
        i -= 1
    return [*parts[:depth], str(i), *parts[depth + 1 :]]


def _locate_for_revert(diff: dict[str, Any], doc: Any) -> str:
    path = diff.get("path", "")
    try:
        op = _resolve_op(diff)
        parts = _split_path(path)
    except DiffApplyError:
        return path
    if op == "delete" or not parts:
        return path  # re-insert of old_value: nothing to check
    n = _list_prefix_len(doc, parts)
    if n is None:
        return path
    want = diff.get("new_value")
    if _current_value(doc, parts) == (True, want):
        return path
    head, tail = parts[: n - 1], parts[n:]
    _, items = _current_value(doc, head)
    matches = [
        j
        for j in range(len(items))
        if _current_value(doc, [*head, str(j), *tail]) == (True, want)
    ]
    if len(matches) != 1:
        raise DiffApplyError(
            f"cannot find the element this change produced at {path!r}"
            + (" (several match)" if matches else "")
        )
    new_path = _join_path([*head, str(matches[0]), *tail])
    logger.info("revert relocated %s -> %s", path, new_path)
    return new_path


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


_MERGED = "__merged_entries__"
_ENTRY_KEYS = {"path", "operation", "op"}


def _split_merged_entries(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """object_pairs_hook: an object whose diff keys repeat is several diff
    entries the model ran together without "}, {" (nvidia nemotron
    2026-11-23: {"path": a, "operation": "add", "new_value": x, "path": b,
    ...} for 4 roles; plain json keeps only the LAST, so 3 were lost).
    Split at each repeat of the object's first key."""
    keys = [k for k, _ in pairs]
    first = keys[0] if keys else None
    if first not in _ENTRY_KEYS or keys.count(first) < 2:
        return dict(pairs)
    chunks: list[dict[str, Any]] = []
    for key, value in pairs:
        if key == first or not chunks:
            chunks.append({})
        chunks[-1][key] = value
    return {_MERGED: chunks}


def _flatten_entries(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in items:
        if isinstance(item, dict) and _MERGED in item:
            out.extend(item[_MERGED])
        else:
            out.append(item)
    return out


def _coerce_diffs(value: Any) -> tuple[list[dict[str, Any]], str] | None:
    """Interpret a parsed JSON value as diff output. None = not diff-shaped."""
    if isinstance(value, dict) and _MERGED in value:
        value = value[_MERGED]
    if isinstance(value, list):
        value = _flatten_entries(value)
        entries = [e for e in (normalize_entry(d) for d in value) if e is not None]
        if entries or all(isinstance(d, dict) for d in value):
            return entries, ""
        return None
    if isinstance(value, dict):
        if isinstance(value.get("diffs"), list):
            entries = [
                e
                for e in (normalize_entry(d) for d in _flatten_entries(value["diffs"]))
                if e is not None
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


_ENTRY_START_RE = re.compile(r'\{\s*"(?:path|operation|op)"\s*:')


def _close_unclosed_entry(
    text: str, pos: int, decoder: "json.JSONDecoder"
) -> tuple[Any, int]:
    """A diff entry missing its own closing brace, e.g.
    {"path": "/roles/-", ..., "new_value": {...}}, {"path": ...  (nvidia
    nemotron 2026-11-23: every entry of a 4-role answer). When decoding
    stops right where the next entry or the closing "]" starts, close the
    entry there and retry. Returns (value, consumed) or (None, 0)."""
    if not _ENTRY_START_RE.match(text) or pos <= 0:
        return None, 0
    rest = text[pos:].lstrip()
    if not (rest.startswith("{") or rest.startswith("]")):
        return None, 0
    head = text[:pos].rstrip().rstrip(",")
    try:
        value, _ = decoder.raw_decode(head + "}")
    except ValueError:
        return None, 0
    return value, pos


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
        except json.JSONDecodeError as exc:
            value, end = _close_unclosed_entry(text[i:], exc.pos, decoder)
            if value is None:
                i += 1
                continue
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict) and _MERGED in value:
            merged = [e for e in map(normalize_entry, value[_MERGED]) if e]
            if merged:
                entries.extend(merged)
                i += end
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

    decoder = json.JSONDecoder(object_pairs_hook=_split_merged_entries)
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
