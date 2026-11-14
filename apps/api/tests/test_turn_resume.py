"""Failed turns + resume (PRD B §5 B-40..B-47, ADR-0028).

Drives the real FastAPI app and the real gateway tool loop; only the
provider call (``litellm.acompletion``), the deployment and the turn plan
are stubbed, so each test scripts exactly which lookup round fails and how.
Synthetic document only.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import litellm
import pytest

from src.json_ai_studio.json_tools import JsonToolbox
from src.json_ai_studio.services import chat_history_service as history
from src.json_ai_studio.services import turn_trace
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.services.turn_planner import TurnPlan

DOC = {
    "entries": [
        {"name": f"entry {i}", "text": f"Synthetic text number {i}."} for i in range(5)
    ]
}


def _response(content: str = "", calls=()):
    tool_calls = [
        SimpleNamespace(
            id=f"c{uuid.uuid4().hex[:6]}",
            function=SimpleNamespace(name=n, arguments=json.dumps(a)),
        )
        for n, a in calls
    ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _read(path: str):
    return _response(calls=[("read", {"path": path})])


def _answer(diffs=(), explanation="Done."):
    return _response(
        content=json.dumps({"diffs": list(diffs), "explanation": explanation})
    )


def _boom():
    return RuntimeError("synthetic provider failure")


@pytest.fixture
def world(monkeypatch):
    """Fake deployment + scripted provider + a forced skeleton/tools plan."""
    from fastapi.testclient import TestClient

    from src.json_ai_studio import gateway as gw
    from src.json_ai_studio.main import app
    from src.json_ai_studio.services import chat_service

    deployment = SimpleNamespace(
        name="fake",
        model_prefix="fake/",
        base_model="m",
        base_url="http://fake",
        api_key="",
        supports_tools=True,
        tool_streaming=False,
        litellm_model=lambda m: m,
        completion_params=lambda model, reasoning=None: {},
        pricing=lambda m: (0.0, 0.0),
    )
    monkeypatch.setattr(
        gw.DeploymentRegistry, "pick_default", classmethod(lambda cls: deployment)
    )

    def plan(doc, message, hist, dep, model):
        return TurnPlan(
            "skeleton",
            [
                {"role": "system", "content": "SYS"},
                *hist,
                {"role": "user", "content": message},
            ],
            JsonToolbox(doc),
            3,
            0,
        )

    monkeypatch.setattr(chat_service, "plan_turn", plan)
    script: list[Any] = []
    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kw):
        calls.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        item = script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(gw.litellm, "acompletion", fake_acompletion)
    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    headers = {"X-API-Key": f"test-{uuid.uuid4().hex}"}
    with TestClient(app, headers=headers) as client:
        sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
        resp = client.post(
            "/api/json/upload",
            files={"json_body": (None, json.dumps(DOC)), "session_id": (None, sid)},
        )
        assert resp.status_code == 200
        yield SimpleNamespace(
            client=client, sid=sid, script=script, calls=calls, gw=gw, dep=deployment
        )


def _events(resp) -> list[tuple[str | None, Any]]:
    assert resp.status_code == 200, resp.text
    return [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]


def chat(w, message="Fix the typo in entry 2") -> list[tuple[str | None, Any]]:
    return _events(
        w.client.post("/api/chat", data={"session_id": w.sid, "message": message})
    )


def resume(w, turn_id: str):
    return w.client.post(f"/api/sessions/{w.sid}/turns/{turn_id}/resume")


def turns(w) -> list[dict[str, Any]]:
    return w.client.get(f"/api/sessions/{w.sid}").json()["conversation_history"]


async def _session(w) -> dict[str, Any]:
    from src.json_ai_studio.db.session_store import store

    return await store.get_session(w.sid)


def _error(events) -> dict[str, Any]:
    return next(p for e, p in events if e == "error")


def _fail_after_two_reads(w, failure: BaseException | None = None):
    w.script.extend([_read("/entries/0"), _read("/entries/1"), failure or _boom()])
    return chat(w)


# ---------------------------------------------------------------------------
# B-40 / B-41: every failure kind is stored as failed, with a trace
# ---------------------------------------------------------------------------


class TestFailedTurnStored:
    async def test_provider_error_mid_loop(self, world):
        events = _fail_after_two_reads(world)
        names = [e for e, _ in events]
        # error (with turn id) comes before the terminal popup event.
        assert names.index("error") < names.index("service_unavailable")
        err = _error(events)
        assert err["code"] == "provider_error" and err["resumable"] is True

        hist = turns(world)
        assert [t["role"] for t in hist] == ["user", "assistant"]
        failed = hist[1]
        assert failed["id"] == err["turn_id"] and hist[0]["id"] == err["user_turn_id"]
        assert failed["status"] == "failed"
        assert failed["error_code"] == "provider_error"
        assert failed["read_paths"] == ["/entries/0", "/entries/1"]
        assert not failed["diffs"]

        trace = (await _session(world))["turn_traces"][failed["id"]]
        assert trace["round_reached"] == 2 and trace["calls"] == 3
        assert [c["paths"] for c in trace["tool_calls"]] == [
            ["/entries/0"],
            ["/entries/1"],
        ]
        assert all(c["result_chars"] > 0 for c in trace["tool_calls"])
        assert set(trace["tool_calls"][0]["hashes"]) == {"/entries/0"}
        assert trace["json_hash"] == turn_trace.json_hash(DOC)

    async def test_trace_never_on_the_wire(self, world):
        _fail_after_two_reads(world)
        body = world.client.get(f"/api/sessions/{world.sid}").json()
        assert "turn_traces" not in body
        assert "messages_snapshot" not in json.dumps(body)

    def test_call_timeout(self, world):
        events = _fail_after_two_reads(
            world, litellm.Timeout(message="t", model="m", llm_provider="fake")
        )
        assert _error(events)["code"] == "timeout"
        assert turns(world)[1]["error_code"] == "timeout"

    def test_provider_rate_limit(self, world):
        events = _fail_after_two_reads(
            world,
            litellm.RateLimitError(message="quota", llm_provider="fake", model="m"),
        )
        assert _error(events)["code"] == "rate_limit"
        assert events[-1][0] == "rate_limit" and events[-1][1]["scope"] == "model"
        assert turns(world)[1]["status"] == "failed"

    def test_budget_exhausted_mid_loop(self, world, monkeypatch):
        slots = iter([0.0, 0.0, 1e9])
        monkeypatch.setattr(
            world.gw.budget, "claim_slot", lambda dep, model: next(slots)
        )
        world.script.extend([_read("/entries/0"), _read("/entries/1")])
        events = chat(world)
        assert _error(events)["code"] == "rate_limit"
        assert turns(world)[1]["read_paths"] == ["/entries/0", "/entries/1"]

    def test_capacity_stop_before_any_call_stores_nothing(self, world, monkeypatch):
        monkeypatch.setattr(world.gw.budget, "claim_slot", lambda dep, model: 1e9)
        events = chat(world)
        assert "error" not in [e for e, _ in events]
        assert events[-1][0] == "rate_limit"
        assert turns(world) == []  # H-05 unchanged

    def test_internal_error_after_answer(self, world, monkeypatch):
        from src.json_ai_studio.services import chat_service

        def broken(_text):
            raise RuntimeError("synthetic parse bug")

        monkeypatch.setattr(chat_service, "parse_llm_response", broken)
        world.script.append(_answer())
        events = chat(world)
        assert _error(events)["code"] == "internal_error"
        assert events[-1][0] == "complete"
        assert turns(world)[1]["status"] == "failed"

    async def test_client_disconnect_is_interrupted(self, world):
        from src.json_ai_studio.auth import Principal
        from src.json_ai_studio.services import chat_service

        session = await _session(world)
        world.script.extend([_read("/entries/0"), _read("/entries/1"), _answer()])
        principal = Principal(kind="anonymous", quota_key="pool", rate_key="rk")
        stream = chat_service.chat_event_stream(
            session, session["working_json"], "Fix entry 2", principal
        )
        tools = 0
        async for text in stream:
            if parse_sse(text)[0] == "tool":
                tools += 1
                if tools == 2:  # round 1 finished, round 2's lookup running
                    break
        await stream.aclose()

        last = session["conversation_history"][-1]
        assert last["status"] == "interrupted"
        assert last["error_code"] == "interrupted"
        assert session["turn_traces"][last["id"]]["round_reached"] == 1

        # …and it can be continued: round 1 is not re-run.
        world.calls.clear()
        world.script[:] = [_read("/entries/1"), _answer(explanation="ok")]
        events = _events(resume(world, last["id"]))
        assert events[-1][0] == "complete"
        first = world.calls[0]["messages"]
        assert sum(1 for m in first if m["role"] == "tool") == 1
        assert session["conversation_history"][-1]["status"] == "complete"


# ---------------------------------------------------------------------------
# B-42 / B-43: resume continues from the trace, flips the turn in place
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_continues_without_rerunning_rounds(self, world):
        events = _fail_after_two_reads(world)
        failed_id = _error(events)["turn_id"]
        world.calls.clear()
        world.script.append(
            _answer(
                [
                    {
                        "path": "/entries/2/text",
                        "operation": "modify",
                        "old_value": "Synthetic text number 2.",
                        "new_value": "Synthetic text, number 2.",
                    }
                ],
                "Fixed entry 2.",
            )
        )
        events = _events(resume(world, failed_id))
        assert len(world.calls) == 1  # only the missing final round
        sent = world.calls[0]["messages"]
        tool_msgs = [m for m in sent if m["role"] == "tool"]
        assert len(tool_msgs) == 2  # both earlier lookups reused
        assert sent[0]["content"].startswith("SYS")  # fresh system prompt
        assert [m["content"] for m in sent if m["role"] == "user"][0] == (
            "Fix the typo in entry 2"
        )
        done = next(p for e, p in events if e == "complete")
        assert done["assistant_turn_id"] == failed_id
        assert done["working_json"]["entries"][2]["text"] == "Synthetic text, number 2."

        hist = turns(world)
        assert [t["role"] for t in hist] == ["user", "assistant"]  # no new turn
        assert hist[1]["status"] == "complete" and hist[1]["error_code"] is None
        assert hist[1]["content"] == "Fixed entry 2."
        assert [d["status"] for d in hist[1]["diffs"]] == ["pending"]

        again = resume(world, failed_id)
        assert again.status_code == 409
        assert again.json()["detail"]["error"] == "not_resumable"

    def test_resume_that_fails_again_stays_resumable(self, world):
        failed_id = _error(_fail_after_two_reads(world))["turn_id"]
        world.script.extend([_read("/entries/2"), _boom()])
        events = _events(resume(world, failed_id))
        err = _error(events)
        assert err["turn_id"] == failed_id and err["resumable"]
        hist = turns(world)
        assert len(hist) == 2 and hist[1]["status"] == "failed"
        assert hist[1]["read_paths"] == ["/entries/0", "/entries/1", "/entries/2"]
        world.calls.clear()
        world.script.append(_answer())
        _events(resume(world, failed_id))
        assert sum(1 for m in world.calls[0]["messages"] if m["role"] == "tool") == 3

    def test_unknown_turn_is_404(self, world):
        assert resume(world, "nope").status_code == 404

    async def test_trace_gone_is_404(self, world):
        """After a backend restart (or restore) the turn has no trace."""
        failed_id = _error(_fail_after_two_reads(world))["turn_id"]
        (await _session(world))["turn_traces"].clear()
        assert resume(world, failed_id).status_code == 404

    def test_only_the_latest_failed_turn(self, world):
        failed_id = _error(_fail_after_two_reads(world))["turn_id"]
        world.script.append(_answer(explanation="Hello."))
        chat(world, "What is in entry 4?")
        resp = resume(world, failed_id)
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "not_resumable"

    def test_complete_turn_is_409(self, world):
        world.script.append(_answer())
        done = next(p for e, p in chat(world) if e == "complete")
        assert resume(world, done["assistant_turn_id"]).status_code == 409


# ---------------------------------------------------------------------------
# B-44: stale rule
# ---------------------------------------------------------------------------


class TestStaleRule:
    async def test_changed_path_dropped_rest_kept(self, world):
        failed_id = _error(_fail_after_two_reads(world))["turn_id"]
        session = await _session(world)
        doc = json.loads(json.dumps(session["working_json"]))
        doc["entries"][1]["text"] = "Edited elsewhere."
        session["working_json"] = doc
        world.calls.clear()
        world.script.append(_answer())
        _events(resume(world, failed_id))
        tool_msgs = [m for m in world.calls[0]["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 2  # call/result pairing intact
        assert "Synthetic text number 0." in tool_msgs[0]["content"]
        assert "stale" in tool_msgs[1]["content"]
        assert "Synthetic text number 1." not in tool_msgs[1]["content"]

    async def test_nothing_reusable_starts_over(self, world):
        failed_id = _error(_fail_after_two_reads(world))["turn_id"]
        session = await _session(world)
        doc = json.loads(json.dumps(session["working_json"]))
        doc["entries"][0]["text"] = "A."
        doc["entries"][1]["text"] = "B."
        session["working_json"] = doc
        world.calls.clear()
        world.script.extend([_read("/entries/0"), _answer()])
        _events(resume(world, failed_id))
        first = world.calls[0]["messages"]
        assert not [m for m in first if m["role"] == "tool"]
        assert first[-1] == {"role": "user", "content": "Fix the typo in entry 2"}
        assert len(world.calls) == 2


# ---------------------------------------------------------------------------
# B-45 / B-46 / B-47: replay + new message after a failure
# ---------------------------------------------------------------------------


class TestReplay:
    async def test_next_turn_sees_failure_summary_and_trace_dropped(self, world):
        _fail_after_two_reads(world)
        world.calls.clear()
        world.script.append(_answer(explanation="Continued."))
        events = chat(world, "go on from where you stopped")  # B-47: proceeds
        assert events[-1][0] == "complete"
        sent = world.calls[0]["messages"]
        replayed = [m for m in sent if m["role"] == "assistant"]
        assert len(replayed) == 1
        note = json.loads(replayed[0]["content"])
        assert note["diffs"] == []
        assert note["explanation"] == (
            "(previous attempt failed: provider_error; read: /entries/0, /entries/1)"
        )
        assert "Synthetic text number 0." not in replayed[0]["content"]
        session = await _session(world)
        assert session["turn_traces"] == {}  # dropped once a turn completed
        assert [t.get("status", "complete") for t in turns(world)[1::2]] == [
            "failed",
            "complete",
        ]

    def test_long_user_messages_head_and_tail_except_latest(self):
        long_a = "A" * 1200 + "MIDDLE" + "Z" * 1200
        long_b = "B" * 3000
        session = {
            "id": "s",
            "conversation_history": [
                history.make_turn("user", long_a),
                history.make_turn("assistant", "ok", diffs=[]),
                history.make_turn("user", long_b),
                history.make_turn("assistant", "ok", diffs=[]),
            ],
        }
        msgs = history.build_history_messages(session)
        first, latest = msgs[0]["content"], msgs[2]["content"]
        assert latest == long_b  # latest replayed user turn stays whole
        assert first.startswith("A" * 1000)
        assert first.endswith("Z" * 300)
        assert "MIDDLE" not in first
        assert f"…({len(long_a) - 1300} chars omitted)" in first

    def test_interrupted_summary_without_reads(self):
        turn = history.make_turn(
            "assistant", "x", status="interrupted", error_code="interrupted"
        )
        assert turn_trace.replay_summary(turn) == (
            "(previous attempt interrupted: interrupted; nothing was read from the document)"
        )


def test_paths_of_call():
    assert turn_trace.paths_of_call("read", '{"path": "/a/1"}', None) == ["/a/1"]
    batch = {"results": [{"path": "/a/4"}, {"path": "/a/5"}]}
    assert turn_trace.paths_of_call("read", '{"paths": ["/a/4..9"]}', batch) == [
        "/a/4",
        "/a/5",
    ]
    assert turn_trace.paths_of_call("search", '{"path_prefix": "/a/3..9"}', None) == [
        "/a"
    ]
    assert turn_trace.paths_of_call("query", '{"path": "/a/*/name"}', None) == ["/a"]
    assert turn_trace.paths_of_call("outline", "{}", None) == [""]
