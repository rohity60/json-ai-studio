"""Job proposal from /api/chat (ADR-0026, PRD C §2).

A whole-document review that does not fit one planned turn is answered
with a `job_proposal` event and no model call; its numbers come from the
packer that sizes the real batches.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.services import job_packing as jp
from src.json_ai_studio.services import review_proposal
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.settings import get_settings

MODEL = "fake/m"
REVIEW_ALL = "Review all entries and fix the spelling"


def big_doc(n: int = 400) -> dict[str, Any]:
    text = " ".join(f"word{i}" for i in range(70))
    return {
        "name": "book",
        "entries": [{"id": i, "keys": [f"k{i}"], "content": text} for i in range(n)],
    }


SMALL_DOC = {"name": "book", "entries": [{"id": 1, "content": "Helo wrld"}]}


def fake_deployment(tpm=16_000):
    return SimpleNamespace(
        name="fake", tpm_input_limit=tpm, min_call_interval_s=15, supports_tools=True
    )


class CountingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def invoke(self, session_id, message, principal, system_prompt, **_kw):
        self.calls += 1
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps({"diffs": [], "explanation": "Looks fine."})}
        ) + "\n\n"


@pytest.fixture
def llm(monkeypatch):
    fake = CountingLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


@pytest.fixture
def deployment(monkeypatch):
    d = fake_deployment()
    monkeypatch.setattr(review_proposal, "default_deployment", lambda: (d, MODEL))
    return d


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


def chat(client, sid: str, message: str, **extra):
    resp = client.post(
        "/api/chat", data={"session_id": sid, "message": message, **extra}
    )
    assert resp.status_code == 200
    return [parse_sse(block) for block in resp.text.split("\n\n") if block.strip()]


def event(events, name):
    return next((p for e, p in events if e == name), None)


def test_review_of_a_large_document_returns_a_proposal_without_a_model_call(
    client, llm, deployment
):
    sid = new_session(client, big_doc())
    events = chat(client, sid, REVIEW_ALL)

    assert llm.calls == 0
    names = [e for e, _ in events]
    assert names == ["thinking", "job_proposal", "complete"]
    proposal = event(events, "job_proposal")
    assert set(proposal) == {
        "scope_path",
        "record_count",
        "batch_count",
        "est_tokens",
        "eta_s",
        "instruction",
    }
    assert proposal["scope_path"] == "/entries"
    assert proposal["record_count"] == 400
    assert proposal["instruction"] == REVIEW_ALL


def test_proposal_numbers_are_the_packers(client, llm, deployment):
    doc = big_doc()
    sid = new_session(client, doc)
    proposal = event(chat(client, sid, REVIEW_ALL), "job_proposal")

    plan = jp.plan_job(doc, "/entries", REVIEW_ALL, deployment, MODEL)
    assert proposal["batch_count"] == plan.batch_count > 1
    assert proposal["est_tokens"] == plan.est_tokens
    assert proposal["eta_s"] == plan.eta_s


def test_proposal_changes_with_the_deployment_limit(client, llm, monkeypatch):
    sid = new_session(client, big_doc())
    counts = []
    for tpm in (8_000, 16_000, 64_000):
        d = fake_deployment(tpm)
        monkeypatch.setattr(review_proposal, "default_deployment", lambda: (d, MODEL))
        counts.append(
            event(chat(client, sid, REVIEW_ALL), "job_proposal")["batch_count"]
        )
    assert counts[0] > counts[1] > counts[2]


def test_complete_states_the_numbers_in_plain_words(client, llm, deployment):
    sid = new_session(client, big_doc())
    events = chat(client, sid, REVIEW_ALL)
    proposal, done = event(events, "job_proposal"), event(events, "complete")

    text = done["explanation"]
    assert "400 items" in text
    assert f"{proposal['batch_count']} batches" in text
    assert "min" in text
    assert done["working_json"]["entries"][0]["id"] == 0  # unchanged
    assert done["job_proposal"] == proposal


def test_proposal_turn_is_stored_in_history(client, llm, deployment):
    sid = new_session(client, big_doc())
    events = chat(client, sid, REVIEW_ALL)
    done = event(events, "complete")

    turns = client.get(f"/api/sessions/{sid}").json()["conversation_history"]
    assert [(t["role"], t["kind"]) for t in turns] == [
        ("user", "message"),
        ("assistant", "job_proposal"),
    ]
    assert turns[1]["id"] == done["assistant_turn_id"]
    assert turns[1]["job_proposal"] == event(events, "job_proposal")
    assert not turns[1]["diffs"]


def test_review_that_fits_one_turn_runs_as_a_normal_turn(client, llm, deployment):
    sid = new_session(client, SMALL_DOC)
    events = chat(client, sid, REVIEW_ALL)

    assert llm.calls == 1
    assert event(events, "job_proposal") is None
    assert event(events, "complete")["explanation"] == "Looks fine."


@pytest.mark.parametrize(
    "message",
    ["fix entry 5", "set all ids to 0", "how many entries are there?"],
)
def test_other_intents_on_a_large_document_go_to_the_model(
    client, llm, deployment, message
):
    sid = new_session(client, big_doc())
    events = chat(client, sid, message)

    assert llm.calls == 1
    assert event(events, "job_proposal") is None


def test_focus_path_turns_are_not_turned_into_jobs(client, llm, deployment):
    sid = new_session(client, big_doc())
    events = chat(client, sid, REVIEW_ALL, focus_path="/entries")
    assert llm.calls == 1 and event(events, "job_proposal") is None


def test_disabled_by_setting(client, llm, deployment, monkeypatch):
    monkeypatch.setenv("INTENT_REVIEW_ENABLED", "false")
    get_settings.cache_clear()
    sid = new_session(client, big_doc())
    assert event(chat(client, sid, REVIEW_ALL), "job_proposal") is None
    assert llm.calls == 1


def test_no_enabled_deployment_falls_back_to_the_normal_turn(client, llm, monkeypatch):
    monkeypatch.setattr(review_proposal, "default_deployment", lambda: None)
    sid = new_session(client, big_doc())
    assert event(chat(client, sid, REVIEW_ALL), "job_proposal") is None
    assert llm.calls == 1
