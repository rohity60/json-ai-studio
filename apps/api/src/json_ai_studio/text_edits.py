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

import re
from difflib import SequenceMatcher
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


# Characters the model often retypes differently: curly vs straight quotes,
# the ellipsis character vs three dots, dash variants.
_CHAR_CLASSES = {
    "'": "['‘’]",
    "‘": "['‘’]",
    "’": "['‘’]",
    '"': '["“”]',
    "“": '["“”]',
    "”": '["“”]',
    "-": "[-–—]",
    "–": "[-–—]",
    "—": "[-–—]",
}

# A find this close to the whole value (length and similarity) that matches
# nowhere exactly is a rewrite of the whole value (prod 2026-11-25: "translate
# the entire script" sent the 12k-char prompt as find, retyped with small
# differences → "not found", 3,914 output tokens lost).
WHOLE_LEN_RATIO = 0.8
WHOLE_SIMILARITY = 0.9


def _loose_pattern(find: str) -> re.Pattern[str]:
    """Regex for `find` that tolerates whitespace runs, quote and dash
    variants."""
    parts = []
    for token in find.split():
        parts.append("".join(_CHAR_CLASSES.get(c) or re.escape(c) for c in token))
    return re.compile(r"\s+".join(parts))


def _spans(text: str, find: str) -> tuple[list[tuple[int, int]], bool]:
    """Non-overlapping (start, end) matches of `find`: exact first, then
    loose (whitespace / quotes / dashes). Second value: loose was used."""
    spans = []
    at = text.find(find)
    while at >= 0:
        spans.append((at, at + len(find)))
        at = text.find(find, at + len(find))
    if spans or not find.split():
        return spans, False
    return [m.span() for m in _loose_pattern(find).finditer(text)], True


def _splits_word(text: str, spans: list[tuple[int, int]]) -> bool:
    """True when any match starts or ends inside a word.

    Partial-word matches corrupt text (prod 2026-11-12, live evals): a page
    cut at "…scaled with In" made the model replace "with In" → "with
    Intelligence" → "Intelligencetelligence"; "he {{user}}" matched inside
    "the {{user}}" → "tthe". `find` must cover whole words."""
    for start, end in spans:
        head, tail = text[start : start + 1].isalnum(), text[end - 1 : end].isalnum()
        before = text[start - 1 : start] if start > 0 else ""
        after = text[end : end + 1]
        if (head and before.isalnum()) or (tail and after.isalnum()):
            return True
    return False


def _is_whole(text: str, find: str) -> bool:
    """`find` is the whole value retyped with small differences."""
    if len(find) < WHOLE_LEN_RATIO * len(text) or len(text) < WHOLE_LEN_RATIO * len(
        find
    ):
        return False
    a, b = " ".join(text.split()), " ".join(find.split())
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return sm.real_quick_ratio() >= WHOLE_SIMILARITY and (
        sm.quick_ratio() >= WHOLE_SIMILARITY and sm.ratio() >= WHOLE_SIMILARITY
    )


def _replace(text: str, spans: list[tuple[int, int]], replace: str) -> str:
    out, last = [], 0
    for start, end in spans:
        out.append(text[last:start])
        out.append(replace)
        last = end
    out.append(text[last:])
    return "".join(out)


def expand_text_edits(
    diffs: list[dict[str, Any]], doc: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Replace every replace_text entry with one modify diff per path.

    Edits on the same path apply in order, each against the result of the
    previous one. "find" matches exactly, else loosely (whitespace runs,
    quote and dash variants). A find that matches nowhere but is the whole
    value retyped (``_is_whole``) replaces the whole value, with a note. An
    edit fails (with a note) when its path is not a string, its "find" text
    is absent, or it matches more than once without ``"all": true`` — never
    guess which occurrence was meant. A path that
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
            spans, loose = _spans(text, find)
            if not spans and _is_whole(text, find):
                text = replace
                made += 1
                notes.append(
                    f"Text edit on {path}: the quoted text differed slightly from "
                    "the current value, so the whole value was replaced — check "
                    "the change."
                )
            elif not spans:
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} was "
                    "not found."
                )
            elif len(spans) > 1 and not e.get("all"):
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} occurs "
                    f"{len(spans)} times — include more surrounding text."
                )
            elif _splits_word(text, spans):
                notes.append(
                    f"Text edit on {path} not applied: {_short(find)!r} only "
                    "matches part of a word in the text."
                )
            else:
                text = _replace(text, spans, replace)
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
