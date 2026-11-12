"""Batch packing (ADR-0026, PRD C §4): size follows the deployment and the
records — never a fixed record count."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.json_ai_studio.services import deployment_budget as budget
from src.json_ai_studio.services import job_packing as jp

MODEL = "fake/m"


def deployment(tpm=None, context=None, interval=0):
    return SimpleNamespace(
        name="fake",
        tpm_input_limit=tpm,
        context_tokens=context,
        min_call_interval_s=interval,
    )


def words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def entries(sizes: list[int]) -> dict:
    return {
        "name": "book",
        "entries": [{"id": i, "content": words(n)} for i, n in enumerate(sizes)],
    }


def char_sizer(text: str) -> int:
    """1 token per 4 chars: makes expected batch contents easy to compute."""
    return len(text) // 4


@pytest.fixture(autouse=True)
def clean_budget():
    budget.reset()
    jp._size_cache.clear()
    yield
    budget.reset()


class TestScopeAndUnits:
    def test_dominant_scope_is_the_big_collection(self):
        assert jp.dominant_scope(entries([50] * 20)) == "/entries"

    def test_dominant_scope_descends_through_wrappers(self):
        doc = {"spec": "v2", "data": {"book": {"entries": [{"t": words(40)}] * 30}}}
        assert jp.dominant_scope(doc) == "/data/book/entries"

    def test_no_dominant_collection_reviews_the_parent_members(self):
        doc = {"data": {"a": words(300), "b": words(300), "c": words(300)}}
        assert jp.dominant_scope(doc) == "/data"
        assert [u.path for u in jp.build_units(doc, "/data")] == [
            "/data/a",
            "/data/b",
            "/data/c",
        ]

    def test_long_strings_outside_the_scope_lead(self):
        doc = {"intro": words(200), "tag": "x", "entries": [{"id": 1}, {"id": 2}]}
        units = jp.build_units(doc, "/entries")
        assert [u.path for u in units] == ["/intro", "/entries/0", "/entries/1"]

    def test_object_collection_members_are_units(self):
        doc = {"entries": {"a": {"t": 1}, "b~/c": {"t": 2}}}
        assert [u.path for u in jp.build_units(doc, "/entries")] == [
            "/entries/a",
            "/entries/b~0~1c",
        ]


class TestRoom:
    def test_room_follows_the_per_minute_budget(self):
        small = jp.batch_room(deployment(tpm=16_000), MODEL, overhead=1_500)
        large = jp.batch_room(deployment(tpm=32_000), MODEL, overhead=1_500)
        # usable = 0.8 × limit; reserve = 10 % of usable (Settings defaults).
        assert small == int(12_800 - 1_500 - 1_280)
        assert large > small

    def test_room_is_bounded_by_the_context_window(self):
        room = jp.batch_room(deployment(context=20_000), MODEL, overhead=1_500)
        assert room == 20_000 - 16_384 - 1_500  # window − reserved output − overhead

    def test_room_is_bounded_by_what_the_model_can_answer(self):
        room = jp.batch_room(deployment(tpm=1_000_000), MODEL, overhead=1_500)
        assert room == 16_384  # llm_max_tokens × job_input_per_output

    def test_room_without_any_known_limit(self):
        assert jp.batch_room(deployment(), MODEL, overhead=1_500) == 8_000

    def test_calibration_shrinks_what_fits(self):
        d = deployment(tpm=16_000)
        sizer = jp.make_sizer(d, MODEL)
        before = sizer(words(500))
        budget._ratio[budget.budget_key(d, MODEL)] = 2.0  # provider counts 2×
        assert jp.make_sizer(d, MODEL)(words(500)) == pytest.approx(2 * before, abs=1)


class TestPacking:
    def test_batches_change_with_the_room(self):
        units = jp.build_units(entries([60] * 40), "/entries")
        few = jp.simulate(units, 2_000, char_sizer)
        many = jp.simulate(units, 500, char_sizer)
        assert len(many) > len(few)
        assert len(few[0].items) > len(many[0].items)

    def test_batches_change_with_record_sizes(self):
        # Same room, records of very different sizes: the record count per
        # batch follows the sizes.
        units = jp.build_units(entries([10] * 12 + [200] * 4), "/entries")
        batches = jp.simulate(units, 600, char_sizer)
        counts = [len(b.items) for b in batches]
        assert counts[0] > counts[-1] >= 1
        assert all(b.tokens <= 600 for b in batches)

    def test_every_unit_is_packed_once_in_order(self):
        units = jp.build_units(entries([30, 80, 15, 200, 5, 60] * 10), "/entries")
        batches = jp.simulate(units, 400, char_sizer)
        packed = [item.path for b in batches for item in b.items]
        assert packed == [u.path for u in units]
        assert batches[-1].cursor == len(units)
        for prev, nxt in zip(batches, batches[1:]):
            assert nxt.start == prev.cursor

    def test_optional_record_cap(self):
        units = jp.build_units(entries([5] * 30), "/entries")
        batches = jp.simulate(units, 10_000, char_sizer, max_records=7)
        assert [len(b.items) for b in batches] == [7, 7, 7, 7, 2]

    def test_oversized_record_is_paged(self):
        text = words(2_000)  # ~3,000 tokens at 4 chars/token
        doc = {
            "entries": [
                {"id": 0, "content": words(20)},
                {"id": 1, "title": "big", "content": text},
                {"id": 2, "content": words(20)},
            ]
        }
        units = jp.build_units(doc, "/entries")
        batches = jp.simulate(units, 800, char_sizer)

        pages = [i for b in batches for i in b.items if i.path == "/entries/1/content"]
        assert len(pages) >= 4
        assert all(p.text is not None and p.length == len(text) for p in pages)
        # Pages are contiguous, cover the whole string, never split a word.
        assert "".join(p.text for p in pages) == text
        assert [p.offset for p in pages] == [
            sum(len(q.text) for q in pages[:n]) for n in range(len(pages))
        ]
        for p in pages[:-1]:
            assert p.text.endswith(" ")
        # The record's small fields travel as whole leaves.
        leaves = {i.path: i.value for b in batches for i in b.items if i.text is None}
        assert leaves["/entries/1/id"] == 1 and leaves["/entries/1/title"] == "big"
        # Its neighbours are still whole records, and nothing is over budget.
        assert leaves["/entries/0"]["id"] == 0 and leaves["/entries/2"]["id"] == 2
        assert all(b.tokens <= 800 for b in batches)
        # While a record is split the cursor stays on it, with a sub-cursor.
        mid = next(b for b in batches if b.sub is not None)
        assert mid.cursor == 1

    def test_resume_inside_a_split_record(self):
        doc = {"entries": [{"content": words(2_000)}, {"content": words(10)}]}
        units = jp.build_units(doc, "/entries")
        first = jp.pack_next(units, 0, None, 800, char_sizer)
        assert first.sub is not None
        second = jp.pack_next(units, first.cursor, first.sub, 800, char_sizer)
        assert second.items[0].offset == len(first.items[-1].text)

    def test_rendered_item_carries_its_json_pointer(self):
        units = jp.build_units(entries([5, 5]), "/entries")
        batch = jp.pack_next(units, 0, None, 1_000, char_sizer)
        assert batch.items[1].render().startswith('{"path":"/entries/1","value":{')


class TestLeanPrompt:
    def test_prompt_has_instruction_contract_and_records_only(self):
        units = jp.build_units(entries([5, 5]), "/entries")
        batch = jp.pack_next(units, 0, None, 1_000, char_sizer)
        system, user = jp.lean_messages("Fix the spelling.", batch.items)
        assert "Fix the spelling." in system["content"]
        assert "replace_text" in system["content"]
        assert user["content"].count('"path":"/entries/') == 2
        # No skeleton, no history, no tool instructions.
        assert "CURRENT WORKING JSON" not in system["content"]
        assert "search" not in system["content"].lower()

    def test_prompt_size_does_not_grow_with_the_document(self):
        d = deployment(tpm=16_000)
        small = jp.overhead_tokens(d, MODEL, "Fix the spelling.")
        assert small == jp.overhead_tokens(d, MODEL, "Fix the spelling.")
        assert small >= 1_500  # Settings floor


class TestPlan:
    def test_plan_matches_a_simulated_run(self):
        doc = entries([40, 90, 20, 300, 10] * 30)
        d = deployment(tpm=16_000, interval=15)
        plan = jp.plan_job(doc, "/entries", "Fix the spelling.", d, MODEL)

        overhead = jp.overhead_tokens(d, MODEL, "Fix the spelling.")
        batches = jp.simulate(
            jp.build_units(doc, "/entries"),
            jp.batch_room(d, MODEL, overhead),
            jp.make_sizer(d, MODEL),
        )
        assert plan.record_count == 150
        assert plan.batch_count == len(batches)
        assert plan.est_tokens == sum(b.tokens + overhead for b in batches)

    def test_tighter_deployment_needs_more_batches_and_time(self):
        doc = entries([120] * 200)
        tight = jp.plan_job(doc, "/entries", "x", deployment(tpm=8_000), MODEL)
        loose = jp.plan_job(doc, "/entries", "x", deployment(tpm=64_000), MODEL)
        assert tight.batch_count > loose.batch_count
        assert tight.eta_s > loose.eta_s

    def test_eta_adds_call_time_and_window_share(self):
        # Tokens count from when a call finishes, so the next batch waits
        # for the call AND its share of the window.
        d = deployment(tpm=16_000)  # usable 12,800 per 60 s
        assert jp.batch_seconds(d, 12_800, call_s=5) == pytest.approx(65)
        assert jp.batch_seconds(d, 6_400, call_s=5) == pytest.approx(35)
        assert jp.batch_seconds(deployment(interval=15), 50_000, call_s=5) == 15
        assert jp.batch_seconds(deployment(), 50_000, call_s=5) == 5


def test_text_edit_on_wrong_record_of_the_batch_is_retargeted():
    """Live 2026-11-13 (Nemotron): fixes addressed to a neighbouring record
    (entry 42's typo sent to /entries/22) were dropped."""
    from src.json_ai_studio.services.job_service import _retarget_text_edits

    doc = {
        "entries": [
            {"keys": ["a"], "content": "Plain text one."},
            {"keys": ["b"], "content": "They beleive it. More words."},
            {"keys": ["c"], "content": "Shared words. Shared words."},
            {"keys": ["d"], "content": "Shared words again."},
        ]
    }
    shown = ["/entries/0", "/entries/1", "/entries/2", "/entries/3"]
    edit = {"operation": "replace_text", "replace": "x"}
    out = _retarget_text_edits(
        [
            {**edit, "path": "/entries/0", "find": "They beleive it."},  # wrong record
            {**edit, "path": "/entries/1", "find": "More words."},  # record → field
            {**edit, "path": "/entries/0/content", "find": "Shared words"},  # 2 records
            {**edit, "path": "/entries/0", "find": "not anywhere"},
        ],
        doc,
        shown,
    )
    assert [d["path"] for d in out] == [
        "/entries/1/content",
        "/entries/1/content",
        "/entries/0/content",  # ambiguous: left as is
        "/entries/0",
    ]
    # outside the batch is never searched
    only_first = _retarget_text_edits(
        [{**edit, "path": "/entries/0", "find": "They beleive it."}], doc, shown[:1]
    )
    assert only_first[0]["path"] == "/entries/0"
