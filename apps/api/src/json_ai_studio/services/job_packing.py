"""Batch packing for whole-document review jobs (ADR-0026, PRD C §4).

One function, `pack_next`, sizes every batch — for the real run
(`job_service`) and for the proposal shown before it (`plan_job` simulates
the whole run with it), so the proposal's numbers are the run's numbers.

A batch is never a fixed number of records. Its room, in tokens of
records, comes from the deployment that will serve it:

    min(per-minute budget − prompt overhead − retry reserve,
        context window − prompt overhead,
        llm_max_tokens × job_input_per_output)

and records are packed greedily from the cursor by each record's own
calibrated token size. A record larger than the room is walked leaf by
leaf and its long strings are sent in pages, so it spans several batches.

The prompt is lean (C-34): instruction + output contract + the batch's
records with their JSON Pointer paths. No skeleton, no chat history, no
tools — context stays flat however large the document is.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from ..settings import get_settings
from . import deployment_budget as budget
from .turn_planner import context_budget

logger = logging.getLogger("json_ai_studio.job_packing")

Sizer = Callable[[str], int]

_MIN_ROOM = 256  # tokens; below this the gateway's budget gate decides
_PAGE_SAMPLE_CHARS = 2_000
_WORD_BACKTRACK = 200  # chars searched backwards for a page break


# ---------------------------------------------------------------------------
# Units: what the job reviews, in order
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    path: str  # JSON Pointer
    value: Any


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def _children(node: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        return [(f"{path}/{_esc(str(k))}", v) for k, v in node.items()]
    if isinstance(node, list):
        return [(f"{path}/{i}", v) for i, v in enumerate(node)]
    return []


def resolve(doc: Any, path: str) -> Any:
    """Value at a JSON Pointer; None when it does not resolve."""
    node = doc
    for raw in [p for p in path.split("/")[1:]] if path else []:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def dominant_scope(doc: Any) -> str:
    """The collection that holds most of the document (C-12).

    Descend from the root while one child container holds at least half of
    the document: `{"entries": [876 records]}` → `/entries`; a card whose
    weight is spread over text fields of `/data` → `/data`.
    """
    total = len(_compact(doc))
    path, node = "", doc
    while True:
        heavy = [
            (p, v)
            for p, v in _children(node, path)
            if isinstance(v, (dict, list)) and v and len(_compact(v)) * 2 >= total
        ]
        if not heavy:
            return path
        path, node = heavy[0]


def build_units(doc: Any, scope_path: str) -> list[Unit]:
    """Long strings outside the scope (leading items), then its members."""
    min_chars = get_settings().job_long_string_min_chars
    leading: list[Unit] = []

    def visit(node: Any, path: str) -> None:
        if path == scope_path:
            return
        if isinstance(node, str):
            if len(node) >= min_chars:
                leading.append(Unit(path, node))
            return
        for child_path, child in _children(node, path):
            visit(child, child_path)

    if scope_path:
        visit(doc, "")
    scope = resolve(doc, scope_path)
    return leading + [Unit(p, v) for p, v in _children(scope, scope_path)]


# ---------------------------------------------------------------------------
# Token sizes
# ---------------------------------------------------------------------------

_size_cache: dict[tuple[str, str], int] = {}
_SIZE_CACHE_MAX = 50_000


def make_sizer(deployment: Any, litellm_model: str) -> Sizer:
    """text → calibrated input tokens on this deployment (raw counts cached)."""
    key = budget.budget_key(deployment, litellm_model)

    def size(text: str) -> int:
        cache_key = (litellm_model, hashlib.sha1(text.encode("utf-8")).hexdigest())
        raw = _size_cache.get(cache_key)
        if raw is None:
            raw = budget.estimate_tokens(
                litellm_model, [{"role": "user", "content": text}]
            )
            if len(_size_cache) >= _SIZE_CACHE_MAX:
                _size_cache.clear()
            _size_cache[cache_key] = raw
        return budget.calibrated(key, raw)

    return size


# ---------------------------------------------------------------------------
# Lean prompt (C-34, C-35)
# ---------------------------------------------------------------------------

_SYSTEM = """\
You review records of a JSON document, one batch at a time, and propose \
changes as machine-readable diffs.

TASK (apply it to every record below): __INSTRUCTION__

OUTPUT FORMAT — respond with EXACTLY ONE JSON object and nothing else. No \
markdown, no code fences, no text before or after the object:
{"diffs": [<diff>, ...], "explanation": "<one short sentence: what you changed in this batch>"}
A <diff> is one of:
{"path": "<JSON Pointer to a string>", "operation": "replace_text", "find": "<exact snippet>", "replace": "<new snippet>"}
{"path": "<JSON Pointer>", "operation": "modify", "old_value": <current value>, "new_value": <new value>}
{"path": "<JSON Pointer>", "operation": "add", "old_value": null, "new_value": <value>}
{"path": "<JSON Pointer>", "operation": "delete", "old_value": <current value>, "new_value": null}

RULES:
1. Each record is one line: {"path": "<its JSON Pointer>", "value": <the record>}. A diff path is the record's path PLUS the keys down to the changed value, joined by "/" (escape "/" in a key as "~1", "~" as "~0"). Example: to fix a word in the "content" field of the record {"path": "/entries/7", "value": {"content": "..."}}, use "path": "/entries/7/content" — never just "/entries/7". Only change what is shown in this batch.
2. To change words INSIDE an existing string use "replace_text": "find" is copied EXACTLY from the text, covers WHOLE words and occurs exactly ONCE in that string (add surrounding words if it repeats; "all": true changes every occurrence). Several fixes in one string = several replace_text diffs on the same path.
3. Use "modify" with a full new value only for short values, or to fill a field that is missing or empty. Never rewrite a long string in full.
4. A line with "text_page" shows only PART of a long string (characters "offset".. of "length"). Use only replace_text on its path, only on text you see; a page that starts or ends mid-sentence is not an error.
5. Keep everything the task does not ask to change. Emit a diff ONLY for a value you actually change — never repeat a record or field unchanged (that wastes the output and the answer gets cut off). If nothing needs changing: {"diffs": [], "explanation": "No changes needed."}
"""


@dataclass
class Item:
    path: str
    value: Any = None  # whole value (a record, or a leaf of a split record)
    text: str | None = None  # one page of a long string
    offset: int = 0
    length: int = 0  # full string length when paged
    tokens: int = 0

    def render(self) -> str:
        if self.text is not None:
            return _compact(
                {
                    "path": self.path,
                    "text_page": self.text,
                    "offset": self.offset,
                    "length": self.length,
                }
            )
        return _compact({"path": self.path, "value": self.value})


def lean_messages(instruction: str, items: list[Item]) -> list[dict[str, Any]]:
    system = _SYSTEM.replace("__INSTRUCTION__", instruction.strip())
    records = "\n".join(item.render() for item in items)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "RECORDS:\n" + records},
    ]


def overhead_tokens(deployment: Any, litellm_model: str, instruction: str) -> int:
    """Calibrated tokens of the prompt without records, floored (§6)."""
    key = budget.budget_key(deployment, litellm_model)
    raw = budget.estimate_tokens(litellm_model, lean_messages(instruction, []))
    return max(budget.calibrated(key, raw), get_settings().job_lean_overhead_tokens)


def batch_room(
    deployment: Any, litellm_model: str, overhead: int, shrink: float = 1.0
) -> int:
    """Tokens of records one batch may carry on this deployment (C-30)."""
    settings = get_settings()
    limits: list[float] = [settings.llm_max_tokens * settings.job_input_per_output]
    usable = budget.plan_budget(deployment)
    if usable is not None:
        reserve = usable * settings.job_retry_reserve_share
        limits.append(usable - overhead - reserve)
    window = context_budget(deployment, litellm_model)
    if window is not None:
        limits.append(window - overhead)
    if usable is None and window is None:
        limits.append(settings.job_fallback_batch_tokens)
    return max(_MIN_ROOM, int(min(limits) * shrink))


# ---------------------------------------------------------------------------
# Packing (C-31, C-32)
# ---------------------------------------------------------------------------


@dataclass
class Batch:
    items: list[Item] = field(default_factory=list)
    start: int = 0  # first unit index in this batch
    end: int = 0  # last unit index in this batch (inclusive)
    cursor: int = 0  # unit index the next batch starts at
    sub: tuple[int, int] | None = None  # (leaf, char offset) inside units[cursor]
    tokens: int = 0  # calibrated tokens of the records


def _leaves(unit: Unit) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    def visit(node: Any, path: str) -> None:
        children = _children(node, path)
        if not children:
            out.append((path, node))
        for child_path, child in children:
            visit(child, child_path)

    visit(unit.value, unit.path)
    return out


def _page(path: str, text: str, offset: int, room: int, sizer: Sizer) -> Item:
    """The longest page of `text` from `offset` that fits `room` tokens,
    cut at whitespace so a word is never split across pages."""
    sample = text[offset : offset + _PAGE_SAMPLE_CHARS]
    chars_per_token = len(sample) / max(1, sizer(sample))
    size = max(1, int(room * chars_per_token * 0.9))
    while True:
        end = min(len(text), offset + size)
        if end < len(text):
            cut = max(
                text.rfind(" ", max(offset, end - _WORD_BACKTRACK), end),
                text.rfind("\n", max(offset, end - _WORD_BACKTRACK), end),
            )
            if cut > offset:
                end = cut + 1
        item = Item(path, text=text[offset:end], offset=offset, length=len(text))
        item.tokens = sizer(item.render())
        if item.tokens <= room or size <= _WORD_BACKTRACK:
            return item
        size = int(size * 0.8)


def pack_next(
    units: list[Unit],
    cursor: int,
    sub: tuple[int, int] | None,
    room: int,
    sizer: Sizer,
    max_records: int = 0,
) -> Batch:
    """The next batch from `cursor` (and `sub`, inside a split record)."""
    batch = Batch(start=cursor, end=cursor, cursor=cursor)
    items = batch.items
    i = cursor

    def close(next_cursor: int, next_sub: tuple[int, int] | None, last: int) -> Batch:
        batch.cursor, batch.sub, batch.end = next_cursor, next_sub, max(cursor, last)
        return batch

    while i < len(units):
        unit = units[i]
        if sub is None:
            item = Item(unit.path, unit.value)
            item.tokens = sizer(item.render())
            capped = bool(max_records) and len(items) >= max_records
            if batch.tokens + item.tokens <= room and not capped:
                items.append(item)
                batch.tokens += item.tokens
                i += 1
                continue
            if items:
                return close(i, None, i - 1)
            sub = (0, 0)  # larger than a whole batch: split it

        leaves = _leaves(unit)
        leaf, offset = sub
        while leaf < len(leaves):
            path, value = leaves[leaf]
            if offset and not isinstance(value, str):
                offset = 0  # the document changed under a paged string
            if offset == 0:
                item = Item(path, value)
                item.tokens = sizer(item.render())
                if batch.tokens + item.tokens <= room:
                    items.append(item)
                    batch.tokens += item.tokens
                    leaf += 1
                    continue
                if not isinstance(value, str):
                    if items:
                        return close(i, (leaf, 0), i)
                    items.append(item)  # cannot be split further
                    batch.tokens += item.tokens
                    leaf += 1
                    continue
            left = room - batch.tokens
            if items and left * 4 < room:
                return close(i, (leaf, offset), i)  # too little room for a page
            page = _page(path, value, offset, left, sizer)
            items.append(page)
            batch.tokens += page.tokens
            offset += len(page.text or "")
            if offset < len(value):
                return close(i, (leaf, offset), i)
            leaf, offset = leaf + 1, 0
        sub = None
        i += 1
    return close(i, None, i - 1)


# ---------------------------------------------------------------------------
# Whole-job plan (proposal numbers, C-11)
# ---------------------------------------------------------------------------


@dataclass
class JobPlan:
    scope_path: str
    record_count: int
    batch_count: int
    est_tokens: int
    eta_s: int


def batch_seconds(deployment: Any, total_tokens: int, call_s: float) -> float:
    """Wall time one batch of `total_tokens` takes at a sustained pace.

    On a per-minute budget a call's tokens count from when it FINISHES
    (deployment_budget.finish), so the next batch waits for the call
    itself plus this batch's share of the window — they add up (live,
    Google 2026-11-13: ~58 s call + ~58 s window share ≈ 118 s per batch).
    Pacing (min_call_interval_s) is a floor.
    """
    seconds = call_s
    usable = budget.plan_budget(deployment)
    if usable:
        seconds += total_tokens / usable * budget.window_span(deployment)
    return max(seconds, float(getattr(deployment, "min_call_interval_s", 0) or 0))


def simulate(
    units: list[Unit], room: int, sizer: Sizer, max_records: int = 0
) -> list[Batch]:
    """Every batch of a full run, from the first unit to the last."""
    batches: list[Batch] = []
    cursor, sub = 0, None
    while cursor < len(units):
        batch = pack_next(units, cursor, sub, room, sizer, max_records)
        if not batch.items and (batch.cursor, batch.sub) == (cursor, sub):
            break  # defensive: no progress
        batches.append(batch)
        cursor, sub = batch.cursor, batch.sub
    return batches


def plan_job(
    doc: Any,
    scope_path: str,
    instruction: str,
    deployment: Any,
    litellm_model: str,
) -> JobPlan:
    settings = get_settings()
    units = build_units(doc, scope_path)
    overhead = overhead_tokens(deployment, litellm_model, instruction)
    room = batch_room(deployment, litellm_model, overhead)
    sizer = make_sizer(deployment, litellm_model)
    batches = simulate(units, room, sizer, settings.job_max_records_per_batch)
    eta = sum(
        batch_seconds(deployment, b.tokens + overhead, settings.job_est_call_s)
        for b in batches
    )
    plan = JobPlan(
        scope_path=scope_path,
        record_count=len(units),
        batch_count=len(batches),
        est_tokens=sum(b.tokens + overhead for b in batches),
        eta_s=int(math.ceil(eta)),
    )
    logger.info(
        "job plan scope=%s records=%d batches=%d room=%d overhead=%d "
        "est_tokens=%d eta_s=%d",
        plan.scope_path or "/",
        plan.record_count,
        plan.batch_count,
        room,
        overhead,
        plan.est_tokens,
        plan.eta_s,
    )
    return plan
