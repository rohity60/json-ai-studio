"""In-string text edits: find/replace inside one long string value.

A plain "modify" diff must carry a field's FULL new value. For long strings
(character descriptions, prompts, lore entries) the model often saw only a
truncated preview — the skeleton or a size-capped ``read`` — so a full-value
rewrite would drop the unseen text (the edit-safety guard then refuses it,
prod 2026-11-12: 7,485 → 232 chars). A ``replace_text`` entry names only
the snippet to change:

    {"path": "/data/description", "operation": "replace_text",
     "find": "Halfings", "replace": "Halflings"}

The server applies every such entry against the FULL current value and
emits ONE ordinary "modify" diff per field, so the wire format, the diff
viewer and accept/reject are unchanged.
"""

from __future__ import annotations

from typing import Any

from .diff_utils import DiffApplyError, _current_value, _split_path

# LLM output synonyms for the text-edit operation.
TEXT_OPS = frozenset(
    {"replace_text", "text_replace", "find_replace", "replace_in_text", "edit_text"}
)
REPLACE_TEXT = "replace_text"


def normalize_text_edit(entry: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Canonical replace_text entry, or None when "find" is unusable."""
    find = entry.get("find", entry.get("old_text", entry.get("search")))
    replace = entry.get("replace", entry.get("new_text", entry.get("replacement")))
    if not isinstance(find, str) or not find:
        return None
    if replace is None:
        replace = ""
    if not isinstance(replace, str):
        replace = str(replace)
    return {
        "path": path,
        "operation": REPLACE_TEXT,
        "find": find,
        "replace": replace,
        "all": entry.get("all") is True,
    }


def _short(text: str, limit: int = 40) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _splits_word(text: str, find: str) -> bool:
    """True when any match of `find` starts or ends inside a word.

    Partial-word matches corrupt text (prod 2026-11-12, live evals): a page
    cut at "…scaled with In" made the model replace "with In" → "with
    Intelligence" → "Intelligencetelligence"; "he {{user}}" matched inside
    "the {{user}}" → "tthe". `find` must cover whole words."""
    head, tail = find[:1].isalnum(), find[-1:].isalnum()
    at = text.find(find)
    while at >= 0:
        before = text[at - 1 : at] if at > 0 else ""
        after = text[at + len(find) : at + len(find) + 1]
        if (head and before.isalnum()) or (tail and after.isalnum()):
            return True
        at = text.find(find, at + 1)
    return False


def expand_text_edits(
    diffs: list[dict[str, Any]], doc: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Replace every replace_text entry with one modify diff per path.

    Edits on the same path apply in order, each against the result of the
    previous one. An edit fails (with a note) when its path is not a string,
    its "find" text is absent, or it matches more than once without
    ``"all": true`` — never guess which occurrence was meant. A path that
    also has a plain diff keeps the plain diff; its text edits are dropped.
    Returns (diffs, notes).
    """
    plain = [d for d in diffs if d.get("operation") != REPLACE_TEXT]
    edits = [d for d in diffs if d.get("operation") == REPLACE_TEXT]
    if not edits:
        return diffs, []

    taken = {d.get("path") for d in plain}
    notes: list[str] = []
    order: list[str] = []
    by_path: dict[str, list[dict[str, Any]]] = {}
    for e in edits:
        path = e["path"]
        if path in taken:
            notes.append(
                f"Text edit on {path} skipped: the field is already changed "
                "as a whole."
            )
            continue
        if path not in by_path:
            order.append(path)
            by_path[path] = []
        by_path[path].append(e)

    out = list(plain)
    for path in order:
        try:
            _, original = _current_value(doc, _split_path(path))
        except DiffApplyError:
            original = None
        if not isinstance(original, str):
            notes.append(f"Text edit on {path} not applied: it is not a text value.")
            continue
        text = original
        made = 0
        for e in by_path[path]:
            find, replace = e["find"], e["replace"]
            count = text.count(find)
            if count == 0:
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} was "
                    "not found."
                )
            elif count > 1 and not e.get("all"):
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} occurs "
                    f"{count} times — include more surrounding text."
                )
            elif _splits_word(text, find):
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} only "
                    "matches part of a word in the text."
                )
            else:
                text = text.replace(find, replace)
                made += 1
        if made and text != original:
            out.append(
                {
                    "path": path,
                    "operation": "modify",
                    "old_value": original,
                    "new_value": text,
                }
            )
    return out, notes
