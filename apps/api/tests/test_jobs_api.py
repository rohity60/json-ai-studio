"""Review jobs API (ADR-0026, PRD C §3–§4): client-driven batches.

Drives the real FastAPI app with the LLM stubbed at
``GatewayService.invoke``. The stub calls the planner callback with a fake
deployment (so packing runs against limits the test controls), records the
records each batch carried, and answers with one fix per record.
"""

from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.json_ai_studio.db.session_store import store
from src.json_ai_studio.diff_utils import TRUNCATION_REASON
from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.services import deployment_budget as budget
from src.json_ai_studio.services import job_packing as jp
from src.json_ai_studio.services import review_proposal
from src.json_ai_studio.services.chat_service import parse_sse

MODEL = "fake/m"
INSTRUCTION = "Review all entries and fix the spelling"


def fake_deployment(tpm=16_000):
    return SimpleNamespace(
        name="fake", tpm_input_limit=tpm, min_call_interval_s=0, supports_tools=True
    )


def filler(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def book(sizes: list[int]) -> dict[str, Any]:
    return {
        "name": "book",
        "entries": [
            {"id": i, "content": f"teh entry {i} " + filler(n)}
            for i, n in enumerate(sizes)
        ],
    }


def fix_typo(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Default model answer: fix "teh" in every whole record shown."""
    diffs = [
        {
            "path": r["path"] + "/content",
            "operation": "replace_text",
            "find": "teh entry",
            "replace": "the entry",
        }
        for r in records
        if isinstance(r.get("value"), dict)
        and "teh entry" in r["value"].get("content", "")
    ]
    return {"diffs": diffs, "explanation": f"Fixed {len(diffs)} typos."}


class BatchLLM:
    """Scripted stand-in for GatewayService.invoke.

    `script` entries are consumed one per call: None → `reply(records)`;
    "quota" / "fail" → the gateway's terminal events; a str → raw model
    output; a callable → its result for the batch's records.
    """

    def __init__(self) -> None:
        self.deployment = fake_deployment()
        self.script: list[Any] = []
        self.batches: list[list[dict[str, Any]]] = []  # records per job call
        self.systems: list[str] = []
        self.plans: list[Any] = []
        self.chat_calls: list[list[dict[str, Any]]] = []
        self.reply = fix_typo

    async def invoke(self, session_id, message, principal, system_prompt, **kw):
        plan = kw["planner"](self.deployment, MODEL)
        system = plan.messages[0]["content"]
        if not system.startswith("You review records"):  # an /api/chat turn
            self.chat_calls.append(plan.messages)
            yield "event: thinking\ndata: " + json.dumps(
                {"text": json.dumps({"diffs": [], "explanation": "ok"})}
            ) + "\n\n"
            return
        lines = plan.messages[1]["content"].split("\n")[1:]
        records = [json.loads(line) for line in lines if line]
        self.batches.append(records)
        self.systems.append(system)
        self.plans.append(plan)
        step = self.script.pop(0) if self.script else None
        if step == "quota":
            yield "event: rate_limit\ndata: " + json.dumps(
                {"scope": "model", "retry_after": 7}
            ) + "\n\n"
            return
        if step == "fail":
            yield "event: service_unavailable\ndata: " + json.dumps(
                {"scope": "model", "message": "busy"}
            ) + "\n\n"
            return
        if isinstance(step, str):
            text = step
        else:
            text = json.dumps((step or self.reply)(records))
        yield "event: thinking\ndata: " + json.dumps({"text": text}) + "\n\n"


@pytest.fixture(autouse=True)
def clean_budget():
    budget.reset()
    yield
    budget.reset()


@pytest.fixture
def llm(monkeypatch):
    fake = BatchLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    monkeypatch.setattr(
        review_proposal, "default_deployment", lambda: (fake.deployment, MODEL)
    )
    return fake


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    headers = {"X-API-Key": f"test-{uuid.uuid4().hex}"}
    with TestClient(app, headers=headers) as c:
        yield c


def new_session(client, doc) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    resp = client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
    )
    assert resp.status_code == 200
    return sid


def create_job(client, sid, **body):
    return client.post(
        f"/api/sessions/{sid}/jobs",
        json={"scope_path": "/entries", "instruction": INSTRUCTION, **body},
    )


def next_batch(client, sid, job_id):
    resp = client.post(f"/api/sessions/{sid}/jobs/{job_id}/next")
    assert resp.status_code == 200, resp.text
    return [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]


def event(events, name):
    return next((p for e, p in events if e == name), None)


def session_of(client, sid):
    return client.get(f"/api/sessions/{sid}").json()


def run_to_end(client, sid, job_id, limit=200):
    completes = []
    for _ in range(limit):
        done = event(next_batch(client, sid, job_id), "batch_complete")
        assert done is not None
        completes.append(done)
        if done["job"]["status"] == "done":
            return completes
    raise AssertionError("job did not finish")


# Mixed record sizes: ~900 tokens, ~150 tokens, ~3,000 tokens.
SIZES = [300, 40, 40, 900, 40, 300, 40, 40, 40, 900] * 6


@pytest.fixture
def sid(client, llm):
    return new_session(client, book(SIZES))


@pytest.fixture
def job(client, sid):
    resp = create_job(client, sid)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Create / get (C-20, C-22)
# ---------------------------------------------------------------------------


class TestCreate:
    def test_new_job_is_ready_at_cursor_zero(self, client, sid, job):
        assert job["status"] == "ready"
        assert (job["cursor"], job["total"]) == (0, len(SIZES))
        assert (job["batches_done"], job["diffs_pending"]) == (0, 0)
        assert job["scope_path"] == "/entries" and job["batches"] == []
        assert session_of(client, sid)["active_job_id"] == job["id"]
        got = client.get(f"/api/sessions/{sid}/jobs/{job['id']}")
        assert got.status_code == 200 and got.json() == job

    def test_estimate_is_the_packers(self, client, sid, job, llm):
        plan = jp.plan_job(
            session_of(client, sid)["working_json"],
            "/entries",
            INSTRUCTION,
            llm.deployment,
            MODEL,
        )
        assert job["batch_count"] == plan.batch_count
        assert job["eta_s"] == plan.eta_s

    def test_second_active_job_is_refused(self, client, sid, job):
        resp = create_job(client, sid)
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["error"] == "job_active" and detail["job_id"] == job["id"]

    def test_scope_defaults_to_the_dominant_collection(self, client, sid):
        resp = client.post(
            f"/api/sessions/{sid}/jobs", json={"instruction": INSTRUCTION}
        )
        assert resp.status_code == 201 and resp.json()["scope_path"] == "/entries"

    def test_bad_scope_and_unknown_ids(self, client, sid):
        assert create_job(client, sid, scope_path="/name").status_code == 400
        assert create_job(client, sid, scope_path="/nope").status_code == 400
        assert create_job(client, "missing").status_code == 404
        assert client.get(f"/api/sessions/{sid}/jobs/nope").status_code == 404
        assert client.post(f"/api/sessions/{sid}/jobs/nope/next").status_code == 404


# ---------------------------------------------------------------------------
# One batch (C-21, C-25, C-34)
# ---------------------------------------------------------------------------


class TestOneBatch:
    def test_next_processes_exactly_one_batch(self, client, sid, job, llm):
        events = next_batch(client, sid, job["id"])
        assert len(llm.batches) == 1
        shown = [r["path"] for r in llm.batches[0]]
        assert shown == [f"/entries/{i}" for i in range(len(shown))]

        done = event(events, "batch_complete")
        assert done["batch_no"] == 1
        assert done["range"] == [0, len(shown) - 1]
        assert done["cursor"] == len(shown) < done["total"] == len(SIZES)
        assert done["job"]["status"] == "ready"
        assert done["job"]["batches_done"] == 1
        assert isinstance(done["eta_s"], int)

    def test_diffs_are_pending_and_tagged(self, client, sid, job, llm):
        events = next_batch(client, sid, job["id"])
        done = event(events, "batch_complete")
        n = len(llm.batches[0])
        assert len(done["diffs"]) == n
        for d in done["diffs"]:
            assert d["status"] == "pending" and d["operation"] == "modify"
            assert (d["job_id"], d["batch_no"]) == (job["id"], 1)
        assert [p["entry"]["id"] for e, p in events if e == "diff"] == [
            d["id"] for d in done["diffs"]
        ]
        assert done["job"]["diffs_pending"] == n

        state = session_of(client, sid)
        assert state["working_json"]["entries"][0]["content"].startswith("the entry 0")
        assert state["working_json"]["entries"][n]["content"].startswith("teh entry")
        assert state["baseline_json"]["entries"][0]["content"].startswith("teh entry")
        assert done["working_json"] == state["working_json"]

    def test_text_edit_keeps_the_rest_of_the_field(self, client, sid, job):
        before = session_of(client, sid)["working_json"]["entries"][0]["content"]
        next_batch(client, sid, job["id"])
        after = session_of(client, sid)["working_json"]["entries"][0]["content"]
        assert after == before.replace("teh entry", "the entry")

    def test_batch_is_a_compact_history_turn(self, client, sid, job, llm):
        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        turn = session_of(client, sid)["conversation_history"][-1]
        n = len(llm.batches[0])
        assert (turn["role"], turn["kind"]) == ("assistant", "job_batch")
        assert turn["content"] == (
            f"Review batch 1: items 1–{n} of {len(SIZES)}, {n} changes."
        )
        assert (turn["job_id"], turn["batch_no"]) == (job["id"], 1)
        assert turn["id"] == done["turn"]["id"]

    def test_prompt_is_lean(self, client, sid, job, llm):
        next_batch(client, sid, job["id"])
        plan, system = llm.plans[0], llm.systems[0]
        assert [m["role"] for m in plan.messages] == ["system", "user"]
        assert plan.toolbox is None and plan.max_rounds == 0
        assert INSTRUCTION in system and "replace_text" in system
        assert "CURRENT WORKING JSON" not in system  # no skeleton / document
        assert "/entries/59" not in plan.messages[1]["content"]  # this batch only

    def test_prompt_stays_flat_over_the_run(self, client, sid, job, llm):
        run_to_end(client, sid, job["id"])
        room = jp.batch_room(
            llm.deployment,
            MODEL,
            jp.overhead_tokens(llm.deployment, MODEL, INSTRUCTION),
        )
        assert len({len(s) for s in llm.systems}) == 1
        assert max(p.raw_estimate for p in llm.plans) <= room + 1_500

    def test_change_outside_the_batch_is_refused(self, client, sid, job, llm):
        llm.script = [
            lambda records: {
                "diffs": [
                    {
                        "path": "/entries/59/content",
                        "operation": "modify",
                        "old_value": "x",
                        "new_value": "hacked",
                    },
                    {
                        "path": "/name",
                        "operation": "modify",
                        "old_value": "book",
                        "new_value": "Book",
                    },
                ],
                "explanation": "x",
            }
        ]
        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        assert [d["status"] for d in done["diffs"]] == ["failed", "failed"]
        assert all("outside this batch" in d["failure_reason"] for d in done["diffs"])
        state = session_of(client, sid)["working_json"]
        assert state["name"] == "book"
        assert state["entries"][59]["content"].startswith("teh entry 59")

    def test_truncated_rewrite_goes_through_the_edit_guard(self, client, llm):
        long_text = filler(600)
        sid = new_session(
            client, {"entries": [{"content": long_text}, {"content": "b"}]}
        )
        job = create_job(client, sid).json()
        llm.script = [
            lambda records: {
                "diffs": [
                    {
                        "path": "/entries/0/content",
                        "operation": "modify",
                        "old_value": long_text,
                        "new_value": long_text[:300] + "…",
                    }
                ],
                "explanation": "rewrote",
            }
        ]
        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        assert done["diffs"][0]["status"] == "failed"
        assert done["diffs"][0]["failure_reason"] == TRUNCATION_REASON
        assert session_of(client, sid)["working_json"]["entries"][0]["content"] == (
            long_text
        )


# ---------------------------------------------------------------------------
# Packing through the API (C-30..C-33)
# ---------------------------------------------------------------------------


class TestPackingInTheRun:
    def test_full_run_covers_every_record_once_and_matches_the_proposal(
        self, client, sid, job, llm
    ):
        completes = run_to_end(client, sid, job["id"])
        seen = [r["path"] for batch in llm.batches for r in batch]
        assert seen == [f"/entries/{i}" for i in range(len(SIZES))]
        # The numbers shown before the run are the run's (same packer).
        assert len(completes) == job["batch_count"]
        final = completes[-1]["job"]
        assert final["status"] == "done"
        assert final["cursor"] == final["total"] == len(SIZES)
        assert final["eta_s"] == 0
        assert [b["batch_no"] for b in final["batches"]] == list(
            range(1, len(completes) + 1)
        )
        assert session_of(client, sid)["active_job_id"] is None

    def test_batch_size_is_not_a_fixed_record_count(self, client, sid, job, llm):
        run_to_end(client, sid, job["id"])
        counts = [len(b) for b in llm.batches]
        assert len(set(counts)) > 1  # follows the records' sizes

    @pytest.mark.parametrize("tpm,expect_more", [(8_000, True), (64_000, False)])
    def test_batch_size_follows_the_deployment_limit(
        self, client, llm, tpm, expect_more
    ):
        sid = new_session(client, book(SIZES))
        baseline = fake_deployment(16_000)
        llm.deployment = baseline
        job = create_job(client, sid).json()
        next_batch(client, sid, job["id"])
        base = len(llm.batches[-1])
        client.delete(f"/api/sessions/{sid}/jobs/{job['id']}")

        sid2 = new_session(client, book(SIZES))
        llm.deployment = fake_deployment(tpm)
        job2 = create_job(client, sid2).json()
        next_batch(client, sid2, job2["id"])
        other = len(llm.batches[-1])
        assert (other < base) if expect_more else (other > base)
        assert (job2["batch_count"] > job["batch_count"]) == expect_more

    def test_calibration_changes_the_next_batch(self, client, sid, job, llm):
        next_batch(client, sid, job["id"])
        first = len(llm.batches[0])
        # The provider counted twice our estimate: later batches shrink.
        budget._ratio[budget.budget_key(llm.deployment, MODEL)] = 2.0
        next_batch(client, sid, job["id"])
        start = first
        same_span_uncalibrated = SIZES[start : start + len(llm.batches[1])]
        assert sum(same_span_uncalibrated) < sum(SIZES[:first])

    def test_oversized_record_is_paged_over_several_batches(self, client, llm):
        text = "teh start " + filler(9_000)  # far beyond one batch
        doc = {
            "entries": [
                {"id": 0, "content": "teh entry 0"},
                {"id": 1, "title": "big", "content": text},
                {"id": 2, "content": "teh entry 2"},
            ]
        }
        sid = new_session(client, doc)
        job = create_job(client, sid).json()

        def fix_pages(records):
            diffs = fix_typo(records)["diffs"]
            for r in records:
                if "text_page" in r and "teh start" in r["text_page"]:
                    diffs.append(
                        {
                            "path": r["path"],
                            "operation": "replace_text",
                            "find": "teh start",
                            "replace": "the start",
                        }
                    )
            return {"diffs": diffs, "explanation": "ok"}

        llm.reply = fix_pages
        completes = run_to_end(client, sid, job["id"])
        assert len(completes) >= 3

        pages = [r for b in llm.batches for r in b if r["path"] == "/entries/1/content"]
        assert len(pages) >= 3 and all("text_page" in p for p in pages)
        assert "".join(p["text_page"] for p in pages) == text
        assert all(p["length"] == len(text) for p in pages)
        # While the record is split the cursor stays on it.
        assert any(c["cursor"] == 1 and c["range"] == [1, 1] for c in completes)
        # A fix found on one page applies to the FULL value; nothing is lost.
        result = session_of(client, sid)["working_json"]["entries"]
        assert result[1]["content"] == text.replace("teh start", "the start")
        assert result[1]["title"] == "big"
        assert result[0]["content"] == "the entry 0"
        assert result[2]["content"] == "the entry 2"

    def test_unprocessed_records_are_reviewed_with_their_current_value(
        self, client, sid, job, llm
    ):
        next_batch(client, sid, job["id"])
        nxt = len(llm.batches[0])
        store._sessions[sid]["working_json"]["entries"][nxt]["content"] = "edited"
        next_batch(client, sid, job["id"])
        assert llm.batches[1][0] == {
            "path": f"/entries/{nxt}",
            "value": {"id": nxt, "content": "edited"},
        }


# ---------------------------------------------------------------------------
# Lifecycle (C-23, C-24, C-27)
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_failed_batch_does_not_advance_and_next_retries_it(
        self, client, sid, job, llm
    ):
        next_batch(client, sid, job["id"])
        cursor = len(llm.batches[0])

        llm.script = ["fail"]
        events = next_batch(client, sid, job["id"])
        failed = event(events, "batch_failed")
        assert event(events, "batch_complete") is None
        assert failed["batch_no"] == 2 and failed["retryable"] is True
        assert failed["job"]["status"] == "failed" and failed["job"]["error"]
        assert failed["job"]["cursor"] == cursor
        assert failed["job"]["batches_done"] == 1
        # Still the session's active job: a new one is refused.
        assert create_job(client, sid).status_code == 409

        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        assert llm.batches[2] == llm.batches[1]  # the same batch again
        assert done["batch_no"] == 2 and done["job"]["status"] == "ready"
        assert done["job"]["error"] is None
        assert done["cursor"] == cursor + len(llm.batches[2])

    def test_quota_event_ends_the_batch_without_advancing(self, client, sid, job, llm):
        llm.script = ["quota"]
        events = next_batch(client, sid, job["id"])
        assert event(events, "rate_limit") == {"scope": "model", "retry_after": 7}
        assert event(events, "batch_complete") is None
        assert event(events, "batch_failed") is None
        got = client.get(f"/api/sessions/{sid}/jobs/{job['id']}").json()
        assert (got["status"], got["cursor"], got["batches_done"]) == ("ready", 0, 0)
        assert session_of(client, sid)["conversation_history"] == []

    def test_cut_off_answer_fails_and_retries_with_a_smaller_batch(
        self, client, sid, job, llm
    ):
        llm.script = ['{"diffs": [{"path": "/entries/0/content", "operat']
        failed = event(next_batch(client, sid, job["id"]), "batch_failed")
        assert "cut off" in failed["error"]
        assert failed["job"]["cursor"] == 0

        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        assert len(llm.batches[1]) < len(llm.batches[0])
        assert llm.batches[1] == llm.batches[0][: len(llm.batches[1])]
        assert done["batch_no"] == 1

    def test_prose_answer_means_no_changes(self, client, sid, job, llm):
        llm.script = ["Everything in this batch looks fine."]
        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        assert done["diffs"] == [] and done["cursor"] == len(llm.batches[0])

    def test_cancel_keeps_pending_diffs(self, client, sid, job, llm):
        done = event(next_batch(client, sid, job["id"]), "batch_complete")
        diff_ids = [d["id"] for d in done["diffs"]]

        resp = client.delete(f"/api/sessions/{sid}/jobs/{job['id']}")
        assert resp.status_code == 200
        cancelled = resp.json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["diffs_pending"] == len(diff_ids)

        state = session_of(client, sid)
        assert state["active_job_id"] is None
        pending = [
            d["id"]
            for t in state["conversation_history"]
            for d in (t["diffs"] or [])
            if d["status"] == "pending"
        ]
        assert pending == diff_ids
        assert state["working_json"]["entries"][0]["content"].startswith("the entry")
        # …and they resolve as usual.
        ok = client.post(f"/api/sessions/{sid}/diffs/{diff_ids[0]}/accept")
        assert ok.status_code == 200
        assert ok.json()["baseline_json"]["entries"][0]["content"].startswith("the ")

        nxt = client.post(f"/api/sessions/{sid}/jobs/{job['id']}/next")
        assert nxt.status_code == 409
        assert nxt.json()["detail"]["error"] == "job_finished"
        assert client.get(f"/api/sessions/{sid}/jobs/{job['id']}").status_code == 200
        assert create_job(client, sid).status_code == 201  # a new job may start

    def test_next_on_a_finished_job_is_refused(self, client, sid, job):
        run_to_end(client, sid, job["id"])
        resp = client.post(f"/api/sessions/{sid}/jobs/{job['id']}/next")
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "job_finished"

    def test_new_upload_cancels_the_job(self, client, sid, job):
        client.post(
            "/api/json/upload",
            files={"json_body": (None, '{"a": 1}'), "session_id": (None, sid)},
        )
        got = client.get(f"/api/sessions/{sid}/jobs/{job['id']}").json()
        assert got["status"] == "cancelled"
        assert session_of(client, sid)["active_job_id"] is None


# ---------------------------------------------------------------------------
# Concurrency with chat (C-26) and history (C-25)
# ---------------------------------------------------------------------------


def mark_running(sid: str, job_id: str) -> None:
    """Put the job in the state it has while a /next stream is open."""
    job = store._sessions[sid]["jobs"][job_id]
    job["status"] = "running"
    job["running_since"] = time.monotonic()


class TestWhileABatchRuns:
    def test_chat_edits_are_refused_questions_are_answered(self, client, sid, job, llm):
        mark_running(sid, job["id"])
        edit = client.post(
            "/api/chat", data={"session_id": sid, "message": "set name to Atlas"}
        )
        assert edit.status_code == 409
        assert edit.json()["detail"]["error"] == "job_running"
        assert "Pause the review" in edit.json()["detail"]["hint"]

        question = client.post(
            "/api/chat", data={"session_id": sid, "message": "how many entries?"}
        )
        assert question.status_code == 200 and len(llm.chat_calls) == 1

    def test_second_next_and_cancel_are_refused(self, client, sid, job):
        mark_running(sid, job["id"])
        nxt = client.post(f"/api/sessions/{sid}/jobs/{job['id']}/next")
        assert nxt.status_code == 409
        assert nxt.json()["detail"]["error"] == "job_running"
        assert client.delete(f"/api/sessions/{sid}/jobs/{job['id']}").status_code == 409
        assert (
            client.get(f"/api/sessions/{sid}/jobs/{job['id']}").json()["status"]
            == "running"
        )

    def test_between_batches_chat_edits_are_allowed(self, client, sid, job, llm):
        next_batch(client, sid, job["id"])
        resp = client.post(
            "/api/chat", data={"session_id": sid, "message": "set name to Atlas"}
        )
        assert resp.status_code == 200

    def test_abandoned_running_flag_does_not_block_forever(self, client, sid, job):
        mark_running(sid, job["id"])
        store._sessions[sid]["jobs"][job["id"]]["running_since"] -= 10_000
        assert (
            client.get(f"/api/sessions/{sid}/jobs/{job['id']}").json()["status"]
            == "ready"
        )
        assert client.post(
            f"/api/sessions/{sid}/jobs/{job['id']}/next"
        ).status_code == (200)

    def test_later_chat_turns_see_one_compact_progress_line(
        self, client, sid, job, llm
    ):
        next_batch(client, sid, job["id"])
        next_batch(client, sid, job["id"])
        client.post("/api/chat", data={"session_id": sid, "message": "what is left?"})

        replayed = llm.chat_calls[0][1:-1]
        assert [m["role"] for m in replayed] == ["user", "assistant"]
        progress = json.loads(replayed[1]["content"])
        assert progress["diffs"] == []
        assert progress["explanation"].startswith("Review batch 2: items ")


# ---------------------------------------------------------------------------
# Per-batch accept / reject
# ---------------------------------------------------------------------------


class TestPerBatchResolve:
    def run_two(self, client, sid, job, llm):
        next_batch(client, sid, job["id"])
        next_batch(client, sid, job["id"])
        return len(llm.batches[0]), len(llm.batches[1])

    def statuses(self, client, sid):
        return {
            t["batch_no"]: {d["status"] for d in t["diffs"]}
            for t in session_of(client, sid)["conversation_history"]
            if t["kind"] == "job_batch"
        }

    def test_reject_one_batch_reverts_only_it(self, client, sid, job, llm):
        n1, n2 = self.run_two(client, sid, job, llm)
        resp = client.post(
            f"/api/sessions/{sid}/diffs/reject-all",
            params={"job_id": job["id"], "batch_no": 1},
        )
        assert resp.status_code == 200
        entries = resp.json()["working_json"]["entries"]
        assert all(e["content"].startswith("teh entry") for e in entries[:n1])
        assert all(e["content"].startswith("the entry") for e in entries[n1 : n1 + n2])
        assert self.statuses(client, sid) == {1: {"rejected"}, 2: {"pending"}}

    def test_accept_one_batch_promotes_only_it(self, client, sid, job, llm):
        n1, n2 = self.run_two(client, sid, job, llm)
        resp = client.post(
            f"/api/sessions/{sid}/diffs/accept-all",
            params={"job_id": job["id"], "batch_no": 2},
        )
        baseline = resp.json()["baseline_json"]["entries"]
        assert all(e["content"].startswith("teh entry") for e in baseline[:n1])
        assert all(e["content"].startswith("the entry") for e in baseline[n1 : n1 + n2])
        assert self.statuses(client, sid) == {1: {"pending"}, 2: {"accepted"}}
        got = client.get(f"/api/sessions/{sid}/jobs/{job['id']}").json()
        assert got["diffs_pending"] == n1

    def test_whole_job_filter_and_unfiltered_calls_still_work(
        self, client, sid, job, llm
    ):
        self.run_two(client, sid, job, llm)
        client.post(
            f"/api/sessions/{sid}/diffs/accept-all", params={"job_id": job["id"]}
        )
        assert self.statuses(client, sid) == {1: {"accepted"}, 2: {"accepted"}}
        next_batch(client, sid, job["id"])
        client.post(f"/api/sessions/{sid}/diffs/reject-all")
        assert self.statuses(client, sid)[3] == {"rejected"}
