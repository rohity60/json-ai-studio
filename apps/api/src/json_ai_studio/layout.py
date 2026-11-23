"""Layout changes in whole-document review jobs.

Live 2026-11-23 (nvidia nemotron, 449 skins, "review all skins and make each
one match this layout exactly: {pack…, skins: [one example skin]}") run as a
review job: batches only see records, never the document's top level, and
the lean prompt had none of chat's layout rules. Results, per batch:
``pack`` copied INTO each skin, whole skins wrapped as ``{pack, skins}``,
25 skins inserted, own names dropped, layouts differing batch to batch.

This module gives a review job what it needs for a layout instruction:

- ``layout_for``: the example's target RECORD (the element of the array the
  job reviews) and its TOP-LEVEL keys the document lacks (``pack``). The
  top-level keys are added once by the server, never by a batch.
- ``prompt_rules``: layout rules for the lean prompt (keep own values, move
  instead of copying, target keys, no wrapping/adding records).
- ``shape_breaks``: checks one batch's RESULT; any break fails the batch and
  the retry gets the problems as a note (the records stay unreviewed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_MAX_EXAMPLES = 3


def parse_example(message: str | None) -> Any | None:
    """First JSON object/array embedded in the message, or None."""
    if not message:
        return None
    decoder = json.JSONDecoder()
    for i, ch in enumerate(message):
        if ch not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(message[i:])
        except ValueError:
            continue
        if isinstance(value, (dict, list)) and value:
            return value
    return None


def _unescape(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


@dataclass
class Layout:
    element: dict[str, Any]  # the example's record (target keys + sample values)
    top_level: dict[str, Any] = field(default_factory=dict)  # root keys to add

    @property
    def keys(self) -> list[str]:
        return list(self.element)

    def to_dict(self) -> dict[str, Any]:
        return {"element": self.element, "top_level": self.top_level}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Layout | None":
        if not data:
            return None
        return cls(element=data["element"], top_level=data.get("top_level") or {})


def layout_for(message: str | None, doc: Any, scope_path: str) -> Layout | None:
    """The target layout when `message` carries a JSON example for the
    records under `scope_path` (an array of objects); else None."""
    example = parse_example(message)
    if example is None:
        return None
    parts = [_unescape(p) for p in scope_path.strip("/").split("/") if p]
    key = parts[-1] if parts else None
    element: Any = None
    top_level: dict[str, Any] = {}
    if isinstance(example, dict) and key in example:
        records = example[key]
        if isinstance(records, list) and records and isinstance(records[0], dict):
            element = records[0]
        # Root keys beside the records array; only for a top-level scope
        # ("/skins"), and only keys the document does not have yet.
        if len(parts) == 1 and isinstance(doc, dict):
            top_level = {k: v for k, v in example.items() if k != key and k not in doc}
    elif isinstance(example, list) and example and isinstance(example[0], dict):
        element = example[0]
    elif isinstance(example, dict) and not any(
        isinstance(v, list) and v and isinstance(v[0], dict) for v in example.values()
    ):
        element = example  # the example IS one record
    if not isinstance(element, dict) or not element:
        return None
    return Layout(element=element, top_level=top_level)


# Worked example in a different domain, so the model learns the mapping
# without being handed values it could copy into the user's records.
_WORKED_EXAMPLE = (
    'Target record {"name": "Song", "artist": "Band", "length": 200}; record '
    '{"path": "/tracks/3", "value": {"title": "Blue Sky", "duration": 245, '
    '"genre": "pop"}} → {"path": "/tracks/3", "operation": "modify", '
    '"new_value": {"name": "Blue Sky", "artist": "Band", "length": 245}} '
    "(title → name and duration → length keep the record's own values; "
    'artist has no counterpart, so the example\'s "Band"; genre fits no key, '
    "so it is left out)."
)


def prompt_rules(layout: Layout) -> str:
    """Layout section of the lean review prompt.

    Live 2026-11-23 (nvidia, 449 skins): answers of one whole-record modify
    per record were right and short; field-level move/add/delete answers
    were 6× longer (cut off more) and sometimes forgot a key with no
    counterpart ("model"). So: one compact whole-record modify per record,
    the exact key list, and the example's value spelled out per key.
    """
    keys = json.dumps(layout.keys)
    defaults = ", ".join(
        f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}"
        for k, v in layout.element.items()
    )
    lines = [
        "",
        "LAYOUT CHANGE — the task gives an example of the target layout. For "
        "this task these rules replace rules 1–3 above:",
        "A. Answer with exactly ONE diff per record: "
        '{"path": "<the record\'s path>", "operation": "modify", "new_value": '
        "<the whole new record>}. No old_value. Compact JSON, no line breaks "
        "or indentation. A record already in the target layout gets no diff.",
        f"B. Every new_value has exactly these keys, in this order: {keys}. "
        "Not one more, not one less.",
        "C. Fill each key from the record's OWN field that means the same "
        "(also when it is named differently or nested), copied VERBATIM — "
        "never reformat it (no added folders, prefixes or file extensions). "
        "ONLY when the record has nothing for a key, use the example's value: "
        f"{defaults}.",
        "D. The record's fields that fit no key are left out.",
        "E. Never add or remove records, never wrap a record in another "
        "object, never put any other part of the example into a record.",
        "Worked example: " + _WORKED_EXAMPLE,
        f"F. Before answering, check every new_value: keys exactly {keys}, "
        "own values copied verbatim.",
    ]
    if layout.top_level:
        top = ", ".join(json.dumps(k) for k in layout.top_level)
        lines.append(
            f"G. The example's top-level {top} is added to the document "
            "separately — do not add it anywhere."
        )
    return "\n".join(lines) + "\n"


def top_level_diffs(layout: Layout, doc: Any) -> list[dict[str, Any]]:
    """Adds for the example's root keys the document still lacks."""
    if not isinstance(doc, dict):
        return []
    return [
        {
            "path": "/" + k.replace("~", "~0").replace("/", "~1"),
            "operation": "add",
            "old_value": None,
            "new_value": v,
        }
        for k, v in layout.top_level.items()
        if k not in doc
    ]


# -- Result checks ----------------------------------------------------------


def _leaf_values(node: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for v in node.values():
            out |= _leaf_values(v)
    elif isinstance(node, list):
        for v in node:
            out |= _leaf_values(v)
    else:
        out.add(json.dumps(node, ensure_ascii=False))
    return out


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 40 else text[:40] + "…"


def shape_breaks(
    before: Any,
    after: Any,
    indices: list[int],
    layout: Layout,
    scope_path: str,
) -> list[str]:
    """Problems with one batch's result for records `indices` of the array.

    Every record must end with exactly the example record's keys (prompt
    rule L1). Live 2026-11-23: checking against the FIRST batch's shape
    instead locked in its mistake (it dropped "model") and then refused a
    later batch that had it right.
    """
    if not (isinstance(before, list) and isinstance(after, list)):
        return []
    if len(before) != len(after):
        return [
            f"records were added or removed ({len(before)} → {len(after)} in "
            f"{scope_path}); change records in place only"
        ]
    allowed = set(layout.element)
    problems: list[str] = []
    extra: dict[str, list[int]] = {}
    not_object: list[int] = []
    lost: dict[str, list[Any]] = {}
    lost_at: dict[str, list[int]] = {}
    for i in indices:
        if i >= len(after):
            continue
        b, a = before[i], after[i]
        if not isinstance(a, dict):
            not_object.append(i)
            continue
        if not isinstance(b, dict) or a == b:
            continue
        for k in set(a) - set(b) - allowed:
            extra.setdefault(k, []).append(i)
        kept = _leaf_values(a)
        for k in set(b) - set(a):
            old = b[k]
            if isinstance(old, (dict, list)):
                continue
            if json.dumps(old, ensure_ascii=False) not in kept:
                lost.setdefault(k, []).append(old)
                lost_at.setdefault(k, []).append(i)
    if not_object:
        problems.append(f"records {not_object[:_MAX_EXAMPLES]} are no longer objects")
    for k, where in sorted(extra.items()):
        problems.append(
            f'records got key "{k}", which is not in the example record '
            f"(e.g. {scope_path}/{where[0]})"
        )
    for k, values in sorted(lost.items()):
        # Own data (values differ record to record) must survive; a field
        # with one shared value ("type": "free") may simply be dropped.
        if len(values) > 1 and len({_short(v) for v in values}) == len(values):
            sample = ", ".join(_short(v) for v in values[:_MAX_EXAMPLES])
            problems.append(
                f'the records\' own "{k}" values were dropped ({sample}); keep '
                "each record's own value under its new key"
            )
    want = set(layout.element)
    missing: dict[str, list[int]] = {}
    for i in indices:
        if i < len(after) and isinstance(after[i], dict):
            for k in want - set(after[i]):
                missing.setdefault(k, []).append(i)
    for k, where in sorted(missing.items()):
        problems.append(
            f'{len(where)} record(s) lack the example\'s key "{k}" (e.g. '
            f"{scope_path}/{where[0]}); add it — with the record's own value if "
            "it has one, else the example's"
        )
    leftover: dict[str, list[int]] = {}
    for i in indices:
        if (
            i < len(after)
            and isinstance(after[i], dict)
            and isinstance(before[i], dict)
        ):
            for k in (set(after[i]) & set(before[i])) - want:
                leftover.setdefault(k, []).append(i)
    for k, where in sorted(leftover.items()):
        problems.append(
            f'{len(where)} record(s) still have "{k}", which the example record '
            f"does not (e.g. {scope_path}/{where[0]}); move its value to its new "
            "key or remove it"
        )
    return problems


def retry_note(problems: list[str], layout: Layout) -> str:
    keys = json.dumps(layout.keys)
    return (
        "Your previous answer for these records broke the target layout: "
        + "; ".join(problems)
        + f". Every record must end with exactly the keys {keys}, keep its own "
        "values (moved under their new keys), and get nothing else."
    )
