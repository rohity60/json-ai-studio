"""Stamp guard: refuse answers that turn distinct records into copies.

Prod 2026-11-22 / live evals 2026-11-23: asked to make 449 skins "match
this layout exactly" (a one-element example), models gave EVERY skin the
example's values ("id": "Steve", "geometry": "models/steve.obj"), wiping
each skin's own name and texture. The diffs looked valid and applied
cleanly; only the result shows the damage.

Signal (checked on the result, so it catches whole-element modifies,
per-field edits and bulk ops alike): an array with at least
``MIN_ELEMENTS`` changed object/array elements that were all DIFFERENT
before and are all IDENTICAL after. Ordinary bulk edits ("set price to 0
for all") leave elements different in their other fields and never fire.
"""

from __future__ import annotations

import json
import re
from typing import Any

MIN_ELEMENTS = 5

KEEP_OPTION = "Keep each element's own values, change only the layout"
SAME_OPTION = "Make every element identical"

# The user explicitly wants identical elements (incl. clicking SAME_OPTION).
_OVERRIDE = re.compile(
    r"\b(identical|all the same|exactly the same|same (content|values?|data) "
    r"(for|in|on) (all|every|each))\b",
    re.IGNORECASE,
)


def wants_identical(message: str | None) -> bool:
    return bool(message and _OVERRIDE.search(message))


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def find_stamped_arrays(
    before: Any, after: Any, path: str = "", min_elements: int = MIN_ELEMENTS
) -> list[dict[str, Any]]:
    """Arrays (same path, same length in both) whose changed record elements
    went from all-distinct to all-identical. Returns
    [{"path", "count", "examples"}] — examples are up to 3 old elements."""
    hits: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in before.keys() & after.keys():
            hits += find_stamped_arrays(
                before[k], after[k], f"{path}/{_escape(str(k))}", min_elements
            )
        return hits
    if not (isinstance(before, list) and isinstance(after, list)):
        return hits
    if len(before) == len(after):
        changed = [
            i
            for i, (b, a) in enumerate(zip(before, after))
            if b != a and isinstance(b, (dict, list)) and isinstance(a, (dict, list))
        ]
        if len(changed) >= min_elements:
            new = {_key(after[i]) for i in changed}
            old = {_key(before[i]) for i in changed}
            if len(new) == 1 and len(old) == len(changed):
                hits.append(
                    {
                        "path": path or "/",
                        "count": len(changed),
                        "examples": [before[i] for i in changed[:3]],
                    }
                )
                return hits  # don't also report its inner arrays
        for i, (b, a) in enumerate(zip(before, after)):
            hits += find_stamped_arrays(b, a, f"{path}/{i}", min_elements)
    return hits


def _label(element: Any) -> str:
    """Short identity of an old element for the note (first string field)."""
    if isinstance(element, dict):
        for v in element.values():
            if isinstance(v, str) and v:
                return v if len(v) <= 30 else v[:30] + "…"
    return _key(element)[:30]


def stamp_note(hits: list[dict[str, Any]]) -> str:
    parts = []
    for h in hits:
        names = ", ".join(f"'{_label(e)}'" for e in h["examples"])
        parts.append(
            f"all {h['count']} elements of {h['path']} the same content, "
            f"replacing each one's own values (e.g. {names})"
        )
    return (
        "Not applied: these changes would give "
        + "; ".join(parts)
        + ". If you meant to change only the layout, I can keep each "
        "element's own values; if you really want identical elements, say so."
    )


def stamp_question(hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": f"Keep each element's own values in {hits[0]['path']}?",
        "options": [KEEP_OPTION, SAME_OPTION],
    }


def touches(diff_path: Any, arrays: list[str]) -> bool:
    """True when a diff edits an element (or deeper) of one of the arrays."""
    if not isinstance(diff_path, str):
        return False
    return any(diff_path.startswith(a.rstrip("/") + "/") for a in arrays)


# -- Example-value stamp: one field of every element set to the example's ---
#
# Live evals 2026-11-23 (nvidia nemotron, 449 skins, "match this layout
# exactly" + a one-element example): ids were mapped correctly but every
# skin's own "geometry" ("geometry.a0", "geometry.a1", …) became the
# example's "models/steve.obj". Elements stay different (their ids differ),
# so find_stamped_arrays cannot see it. Signal: a leaf that was present and
# all-different across >= MIN_ELEMENTS changed elements becomes one value,
# and that value appears inside a JSON example in the user's message. "Set
# price to 0 for all" has no JSON example and never fires.

EXAMPLE_KEEP_OPTION = "Keep each element's own values for those fields"
EXAMPLE_USE_OPTION = "Use the example's values for every element"

_USE_EXAMPLE = re.compile(
    r"\buse the example'?s? values? (for|in|on) (every|all|each)\b", re.IGNORECASE
)


def wants_example_values(message: str | None) -> bool:
    return bool(message and _USE_EXAMPLE.search(message))


def _example_text(message: str | None) -> str:
    """The part of the message from the first JSON bracket on ('' if none)."""
    if not message:
        return ""
    starts = [i for i in (message.find("{"), message.find("[")) if i >= 0]
    return message[min(starts) :] if starts else ""


def _leaves(node: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            out.update(_leaves(v, f"{prefix}/{_escape(str(k))}"))
        return out
    return {prefix: node}


def _in_example(value: Any, example: str) -> bool:
    if isinstance(value, bool) or value is None:
        return False  # too common to mean "copied from the example"
    if isinstance(value, str):
        return len(value) >= 2 and json.dumps(value) in example
    if isinstance(value, (int, float)):
        return (
            re.search(rf"(?<![\w.]){re.escape(str(value))}(?![\w.])", example)
            is not None
        )
    return False


def find_example_stamps(
    before: Any,
    after: Any,
    message: str | None,
    path: str = "",
    min_elements: int = MIN_ELEMENTS,
) -> list[dict[str, Any]]:
    """[{"path", "field", "value", "count", "examples"}] per stamped field."""
    example = _example_text(message)
    if not example:
        return []
    hits: list[dict[str, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in before.keys() & after.keys():
            hits += find_example_stamps(
                before[k], after[k], message, f"{path}/{_escape(str(k))}", min_elements
            )
        return hits
    if not (isinstance(before, list) and isinstance(after, list)):
        return hits
    if len(before) != len(after):
        return hits
    changed = [
        i
        for i, (b, a) in enumerate(zip(before, after))
        if b != a and isinstance(b, dict) and isinstance(a, dict)
    ]
    if len(changed) >= min_elements:
        old_leaves = [_leaves(before[i]) for i in changed]
        new_leaves = [_leaves(after[i]) for i in changed]
        for field in new_leaves[0]:
            new_vals = [nl.get(field, _ABSENT) for nl in new_leaves]
            value = new_vals[0]
            if any(v is _ABSENT for v in new_vals):
                continue  # not every element has it: not one stamped value
            if any(_key(v) != _key(value) for v in new_vals):
                continue
            old_vals = [ol.get(field, _ABSENT) for ol in old_leaves]
            if any(v is _ABSENT for v in old_vals):
                continue  # a new field: the example's value is expected
            if len({_key(v) for v in old_vals}) != len(old_vals):
                continue  # old values were not all different
            if not _in_example(value, example):
                continue
            hits.append(
                {
                    "path": path or "/",
                    "field": field.lstrip("/"),
                    "value": value,
                    "count": len(changed),
                    "examples": old_vals[:3],
                }
            )
        if hits:
            return hits
    for i, (b, a) in enumerate(zip(before, after)):
        hits += find_example_stamps(b, a, message, f"{path}/{i}", min_elements)
    return hits


_ABSENT = object()


def example_note(hits: list[dict[str, Any]]) -> str:
    parts = [
        f"{h['field']} in all {h['count']} elements of {h['path']} would become "
        f"the example's {json.dumps(h['value'])}, replacing each one's own value "
        f"(e.g. {', '.join(json.dumps(v) for v in h['examples'])})"
        for h in hits
    ]
    return (
        "Not applied yet: "
        + "; ".join(parts)
        + ". Should each element keep its own value, or take the example's?"
    )


_GUIDANCE = {
    KEEP_OPTION: (
        "Keep each element's own values: a field the element already has "
        "(also under a new name or place) keeps its value; take from the "
        "example only the layout and the fields the element lacks. Never "
        "copy the example's values over the element's own."
    ),
    EXAMPLE_USE_OPTION: "Use the example's values for every element.",
    SAME_OPTION: "Make every element identical to the example.",
}
_GUIDANCE[EXAMPLE_KEEP_OPTION] = _GUIDANCE[KEEP_OPTION]
GUIDANCE_MAX_CHARS = 1_000


def guidance_text(answer: str) -> str:
    """Instruction text for the user's answer to a guard question.

    A known option maps to a precise instruction (the "use"/"identical"
    ones contain the override wording, so the guards then let the change
    through); free text is passed on as typed.
    """
    answer = answer.strip()
    return _GUIDANCE.get(answer, answer[:GUIDANCE_MAX_CHARS])


def example_question(hits: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ", ".join(sorted({h["field"] for h in hits}))
    return {
        "text": f"Keep each element's own {fields}, or use the example's value for all?",
        "options": [EXAMPLE_KEEP_OPTION, EXAMPLE_USE_OPTION],
    }
