"""One model answer → applied changes. Shared by chat turns and review batches.

Both callers parse the model's output themselves (chat also reads bulk ops,
questions and tool rounds; a review batch reads only plain diffs), then run
the same two steps:

1. ``expand_answer`` — turn every shorthand into ordinary diffs against the
   FULL current document: text edits (``replace_text``), moves / renames,
   plain diffs with ``*`` (routed to bulk), bulk ops; then drop no-op
   modifies. Wire format afterwards: add / modify / delete only.
2. ``apply_guarded`` — apply (``DiffUtils.apply_all_verbose``: index
   repair, ``$from`` copies, missing parents, held deletes), then check the
   RESULT with the stamp guard and the example-value guard (``guards.py``).
   Diffs touching a flagged array are held back, the rest re-apply; the
   caller gets the note and a question to show.

Anything caller-specific (SSE events, history turns, batch scoping, job
tags, explanation wording) stays with the caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from . import guards
from .bulk_edits import expand_all, split_wildcard_diffs
from .diff_utils import DiffApplyError, DiffUtils, _split_path
from .move_edits import expand_moves
from .text_edits import expand_text_edits

logger = logging.getLogger("json_ai_studio.answer")

MISSING = object()

Diff = dict[str, Any]
Failed = list[tuple[Diff, str]]


def value_at(doc: Any, path: str) -> Any:
    """Value at a JSON Pointer, or MISSING if it does not resolve."""
    try:
        parts = _split_path(path)
    except DiffApplyError:
        return MISSING
    current = doc
    for part in parts:
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


def is_noop(diff: Diff, doc: Any) -> bool:
    """A modify whose new_value equals the document's current value."""
    if diff.get("operation") != "modify" or not diff.get("path"):
        return False
    current = value_at(doc, diff["path"])
    return current is not MISSING and current == diff.get("new_value")


# ---------------------------------------------------------------------------
# Step 1: expand
# ---------------------------------------------------------------------------


@dataclass
class Expanded:
    diffs: list[Diff]
    # Human-readable reasons an edit was refused / matched nothing (text
    # edits, moves, bulk ops), in that order.
    notes: list[str] = field(default_factory=list)
    # Bulk ops that were expanded (the model's own + routed wildcard diffs).
    bulk_ops: list[Diff] = field(default_factory=list)
    bulk_diffs: int = 0
    noops: int = 0


def expand_answer(
    diffs: list[Diff], bulk_ops: list[Diff], doc: Any, max_matches: int
) -> Expanded:
    """Every shorthand in one answer → ordinary add/modify/delete diffs."""
    # Find/replace inside long strings → one full-value modify per field,
    # computed against the FULL value the model may only have seen cut.
    diffs, notes = expand_text_edits(diffs, doc)
    notes = list(notes)
    # Move / rename → add at the target + delete at the source.
    diffs, bulk_ops, move_notes = expand_moves(diffs, bulk_ops, doc, max_matches)
    notes.extend(move_notes)
    # A plain diff with `*` in its path is a bulk op in disguise.
    diffs, wildcard_ops = split_wildcard_diffs(diffs)
    if wildcard_ops:
        logger.info("wildcard diffs routed to bulk count=%d", len(wildcard_ops))
        bulk_ops = [*bulk_ops, *wildcard_ops]
    bulk_count = 0
    if bulk_ops:
        bulk_diffs, op_notes = expand_all(bulk_ops, doc, max_matches)
        notes.extend(op_notes)
        listed = {d.get("path") for d in diffs}  # the model's own diff wins
        extra = [d for d in bulk_diffs if d["path"] not in listed]
        diffs, bulk_count = [*diffs, *extra], len(bulk_diffs)
    # Drop modifies that set a value to what it already is (prod: the model
    # re-emitted an unchanged "ip", which reads as "nothing changed").
    kept = [d for d in diffs if not is_noop(d, doc)]
    return Expanded(
        diffs=kept,
        notes=notes,
        bulk_ops=list(bulk_ops),
        bulk_diffs=bulk_count,
        noops=len(diffs) - len(kept),
    )


# ---------------------------------------------------------------------------
# Step 2: apply + guards
# ---------------------------------------------------------------------------


@dataclass
class Applied:
    merged: Any
    applied: list[Diff]
    failed: Failed
    # Set when a guard held diffs back: why (user-facing), what to ask, and
    # the held diffs (not applied; callers decide whether to show them).
    note: str | None = None
    question: dict[str, Any] | None = None
    held: list[Diff] = field(default_factory=list)


def apply_guarded(
    diffs: list[Diff],
    doc: Any,
    message: str | None,
    min_elements: int = guards.MIN_ELEMENTS,
) -> Applied:
    """Apply `diffs` to `doc`; hold back changes a guard flags.

    `message` is the user's request (chat message / review instruction): it
    holds the JSON example and the explicit overrides ("identical", "use
    the example's values for every …").
    """
    merged, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
    note = question = None
    arrays: list[str] = []
    # Stamp guard: distinct records must not all become one copy (the model
    # stamping a one-element example over every element).
    if not guards.wants_identical(message):
        hits = guards.find_stamped_arrays(doc, merged, min_elements=min_elements)
        if hits:
            arrays = [h["path"] for h in hits]
            note, question = guards.stamp_note(hits), guards.stamp_question(hits)
            summary = ", ".join(f"{h['path']} x{h['count']}" for h in hits)
            logger.warning("stamp guard: %s", summary)
    # Example-value guard: one field of every element overwritten with the
    # value from the user's JSON example (each element's own geometry → the
    # example's "models/steve.obj"). Ask instead of guessing.
    # "Make every element identical" (or the user's own wording for it) also
    # means taking the example's values: without this, the answer to the
    # stamp question was held again by this guard, asking forever.
    if (
        note is None
        and not guards.wants_example_values(message)
        and not guards.wants_identical(message)
    ):
        hits = guards.find_example_stamps(
            doc, merged, message, min_elements=min_elements
        )
        if hits:
            arrays = sorted({h["path"] for h in hits})
            note, question = guards.example_note(hits), guards.example_question(hits)
            summary = ", ".join(f"{h['path']}/{h['field']} x{h['count']}" for h in hits)
            logger.warning("example-value guard: %s", summary)
    if note is None:
        return Applied(merged, applied, failed)
    held = [d for d in diffs if guards.touches(d.get("path"), arrays)]
    keep = [d for d in diffs if not guards.touches(d.get("path"), arrays)]
    logger.warning("guard held %d diff(s) on %s", len(held), arrays)
    merged, applied, failed = DiffUtils.apply_all_verbose(keep, doc)
    return Applied(merged, applied, failed, note, question, held)
