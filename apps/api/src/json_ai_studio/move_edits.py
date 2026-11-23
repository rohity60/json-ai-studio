"""Move / rename: relocate a value without the model copying it.

Without a move op, models restructuring a document (rename a key, nest a
field) either rewrite whole elements or write the NEW KEY NAME as the
value — live evals 2026-11-23 (nvidia nemotron, gemma4) on 449 skins
produced ``"localization_name": "id"`` and ``"texture": "textures.body"``,
destroying every skin's own data. The model may now emit:

    {"operation": "move", "from": "/skins/3/texture", "path": "/skins/3/textures/body"}
    {"operation": "rename", "path": "/skins/3/localization_name", "new_key": "id"}

and, with "*" wildcards (same count in "from" and "path"; the i-th "*" in
"path" is the element the i-th "*" in "from" matched), in "diffs" or
"bulk", optionally with a bulk "where" on the element of the last "*":

    {"operation": "move", "from": "/skins/*/localization_name", "path": "/skins/*/id"}

The server expands each concrete move into ONE "add" at the target (the
value copied from the snapshot) and ONE "delete" at the source, so the wire
format, diff viewer and accept/reject are unchanged. Missing parent objects
of the target are created inside the add. Refused (with a note) when the
target already holds a different value, lies inside the source, or its
parent is not an object/array. A renamed key moves to the end of its
object (JSON key order is not preserved).
"""

from __future__ import annotations

import copy
from typing import Any

from .bulk_edits import BulkEditError, _escape, _matches, _walk, normalize_where
from .diff_utils import DiffApplyError, _current_value, _split_path

MOVE_OPS = frozenset({"move", "move_key", "mv", "relocate"})
RENAME_OPS = frozenset({"rename", "rename_key", "rename_field"})


def is_move(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    op = str(entry.get("operation", "")).strip().lower()
    return op in MOVE_OPS or op in RENAME_OPS


def _join(parts: list[str]) -> str:
    return "/" + "/".join(_escape(p) for p in parts) if parts else ""


def _canonical(entry: dict[str, Any]) -> tuple[str, str] | str:
    """(from, path) pointers, or a reason string when unusable."""
    op = str(entry.get("operation", "")).strip().lower()
    if op in RENAME_OPS:
        src = entry.get("path", entry.get("from"))
        new_key = next(
            (
                entry[k]
                for k in ("new_key", "to", "new_name", "key", "new_value")
                if isinstance(entry.get(k), str) and entry[k]
            ),
            None,
        )
        if not isinstance(src, str) or new_key is None:
            return "rename needs a 'path' and a 'new_key'"
        if new_key.startswith("/"):
            return src, new_key  # a full pointer given as the new name
        parts = _split_path(src)
        if not parts:
            return "cannot rename the document root"
        return src, _join([*parts[:-1], new_key])
    src = entry.get("from", entry.get("source", entry.get("old_path")))
    dst = entry.get("path", entry.get("to", entry.get("target")))
    if not isinstance(src, str) or not isinstance(dst, str):
        return "move needs 'from' and 'path' JSON Pointers"
    return src, dst


def _bind(parts: list[str], keys: list[str]) -> list[str]:
    it = iter(keys)
    return [next(it) if p == "*" else p for p in parts]


def _star_keys(pattern: list[str], concrete: list[str]) -> list[str]:
    return [c for p, c in zip(pattern, concrete) if p == "*"]


def _pairs(
    src: str, dst: str, where: dict[str, Any], doc: Any, max_matches: int
) -> list[tuple[list[str], list[str]]]:
    src_parts, dst_parts = _split_path(src), _split_path(dst)
    if src_parts.count("*") != dst_parts.count("*"):
        raise BulkEditError("'from' and 'path' need the same number of '*' wildcards")
    if "*" not in src_parts:
        return [(src_parts, dst_parts)]
    pairs = []
    for concrete, exists, value, anchor in _walk(doc, src_parts, [], None):
        if not exists:
            continue
        if where and not _matches(where, anchor, value):
            continue
        pairs.append((concrete, _bind(dst_parts, _star_keys(src_parts, concrete))))
        if len(pairs) > max_matches:
            raise BulkEditError(f"move matched more than {max_matches} locations")
    return pairs


class _Planner:
    """Turns concrete (src, dst) pairs into add/delete diffs, merging targets
    that need the same missing parent into one add."""

    def __init__(self, doc: Any) -> None:
        self.doc = doc
        self.diffs: list[dict[str, Any]] = []
        self.created: dict[tuple[str, ...], dict[str, Any]] = {}  # add diffs

    def _in_created(self, dst: list[str]) -> tuple[dict[str, Any], list[str]] | None:
        for n in range(len(dst) - 1, 0, -1):
            hit = self.created.get(tuple(dst[:n]))
            if hit is not None:
                return hit, dst[n:]
        return None

    def plan(self, src: list[str], dst: list[str]) -> str | None:
        """Add the diffs for one move; returns a refusal reason or None."""
        if src == dst:
            return None
        if dst[: len(src)] == src:
            return f"cannot move {_join(src)} into itself"
        found, value = _current_value(self.doc, src)
        if not found:
            return f"{_join(src)} does not exist"
        if not dst:
            return "cannot move onto the document root"
        exists, current = _current_value(self.doc, dst)
        delete = {
            "path": _join(src),
            "operation": "delete",
            "old_value": copy.deepcopy(value),
            "new_value": None,
        }
        if exists:
            if current != value:
                return f"{_join(dst)} already exists with a different value"
            self.diffs.append(delete)  # target already right: only drop source
            return None
        merged = self._in_created(dst)
        if merged is not None:
            add, rest = merged
            node = add["new_value"]
            for part in rest[:-1]:
                if not isinstance(node, dict):
                    return f"cannot create {_join(dst)}"
                node = node.setdefault(part, {})
            if not isinstance(node, dict) or rest[-1] in node:
                return f"{_join(dst)} is set twice"
            node[rest[-1]] = copy.deepcopy(value)
            self.diffs.append(delete)
            return None
        # Deepest existing ancestor of the target.
        k = len(dst) - 1
        while k > 0 and not _current_value(self.doc, dst[:k])[0]:
            k -= 1
        _, parent = _current_value(self.doc, dst[:k])
        if k < len(dst) - 1:  # missing intermediate objects
            if not isinstance(parent, dict):
                return f"cannot create {_join(dst[: k + 1])} inside a non-object"
            new_value: Any = copy.deepcopy(value)
            for part in reversed(dst[k + 1 :]):
                new_value = {part: new_value}
            add = {
                "path": _join(dst[: k + 1]),
                "operation": "add",
                "old_value": None,
                "new_value": new_value,
            }
            self.created[tuple(dst[: k + 1])] = add
        else:
            if not isinstance(parent, (dict, list)):
                return f"{_join(dst[:-1])} is not an object or array"
            add = {
                "path": _join(dst),
                "operation": "add",
                "old_value": None,
                "new_value": copy.deepcopy(value),
            }
            if isinstance(add["new_value"], dict):
                self.created[tuple(dst)] = add
        self.diffs.extend([add, delete])
        return None


def expand_moves(
    diffs: list[dict[str, Any]],
    bulk_ops: list[dict[str, Any]],
    doc: Any,
    max_matches: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Pull move/rename entries out of diffs and bulk ops and expand them.

    Returns (diffs, bulk_ops, notes): the remaining plain diffs plus the
    generated add/delete diffs, the remaining bulk ops, and one note per
    refused move (wildcard moves report a summary). A generated diff whose
    path and operation a plain diff already has is dropped — the model's
    own diff wins."""
    entries = [d for d in diffs if is_move(d)] + [o for o in bulk_ops if is_move(o)]
    if not entries:
        return diffs, bulk_ops, []
    plain = [d for d in diffs if not is_move(d)]
    rest_ops = [o for o in bulk_ops if not is_move(o)]
    planner = _Planner(doc)
    notes: list[str] = []
    for entry in entries:
        canon = _canonical(entry)
        if isinstance(canon, str):
            notes.append(f"Move not applied: {canon}.")
            continue
        src, dst = canon
        where = entry.get("where") or {}
        try:
            where = normalize_where(where) if isinstance(where, dict) else {}
            pairs = _pairs(src, dst, where, doc, max_matches)
        except (BulkEditError, DiffApplyError) as exc:
            notes.append(f"Move {src} → {dst} not applied: {exc}.")
            continue
        refused = [r for s, d in pairs if (r := planner.plan(s, d))]
        wildcard = "*" in src
        if wildcard and not pairs:
            notes.append(f"Move {src} → {dst} matched nothing.")
        elif wildcard and refused:
            notes.append(
                f"Move {src} → {dst}: {len(pairs) - len(refused)} of "
                f"{len(pairs)} applied; skipped e.g. {refused[0]}."
            )
        elif refused:
            notes.append(f"Move {src} → {dst} not applied: {refused[0]}.")
    taken = {(d.get("path"), str(d.get("operation", "")).lower()) for d in plain}
    generated = [d for d in planner.diffs if (d["path"], d["operation"]) not in taken]
    return [*plain, *generated], rest_ops, notes
