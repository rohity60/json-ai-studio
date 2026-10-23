"""Chat history tests (ADR-0021).

Integration tests drive the real FastAPI app over HTTP (TestClient) with the
LLM stubbed at ``GatewayService.invoke``: each stub call records the
messages it was given (system prompt + replayed history) and streams a
canned ``{"diffs": [...], "explanation": ...}`` reply. That exercises the
whole server path — SSE chat, turn persistence, diff status lifecycle,
history replay, clear, version boundary, restore — with no network.

Unit tests cover ``chat_history_service`` replay shaping (compaction,
budgets, boundaries, context fit) directly.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.services import chat_history_service as history
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.settings import get_settings

FLAGS = {
    "flags": {
        "newCheckout": {"enabled": True, "rollout": 25},
        "darkMode": {"enabled": True, "rollout": 100},
        "aiAssistant": {"enabled": False, "rollout": 0},
    }
}


def _modify(path: str, old: Any, new: Any) -> dict[str, Any]:
    return {"path": path, "operation": "modify", "old_value": old, "new_value": new}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeLLM:
    """Scripted stand-in for GatewayService.invoke.

    `replies` are consumed in order; every call is recorded in `calls` as
    {"system", "history", "message"} so tests can assert what the model saw.
    """

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    async def invoke(
        self,
        session_id,
        message,
        principal,
        system_prompt,
        model=None,
        profile=None,
        reasoning=None,
        history=None,
        **_kw,
    ):
        self.calls.append(
            {
                "system": system_prompt,
                "history": list(history or []),
                "message": message,
            }
        )
        reply = self.replies.pop(0)
        if reply.get("_quota"):
            yield "event: rate_limit\ndata: " + json.dumps({"scope": "model"}) + "\n\n"
            return
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(reply)}
        ) + "\n\n"


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    # One test makes far more calls than the anonymous per-minute limit.
    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    headers = {"X-API-Key": f"test-{uuid.uuid4().hex}"}
    with TestClient(app, headers=headers) as c:
        yield c


@pytest.fixture
def session_id(client) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    resp = client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(FLAGS)), "session_id": (None, sid)},
    )
    assert resp.status_code == 200
    return sid


def chat(client, session_id: str, message: str) -> list[tuple[str | None, Any]]:
    """POST /api/chat and return the parsed SSE events."""
    resp = client.post("/api/chat", data={"session_id": session_id, "message": message})
    assert resp.status_code == 200
    return [parse_sse(block) for block in resp.text.split("\n\n") if block.strip()]


def complete_of(events) -> dict[str, Any]:
    return next(p for e, p in events if e == "complete")


def get_history(client, session_id: str) -> list[dict[str, Any]]:
    return client.get(f"/api/sessions/{session_id}").json()["conversation_history"]


def statuses(turns) -> list[str]:
    return [d["status"] for t in turns for d in (t.get("diffs") or [])]


# ---------------------------------------------------------------------------
# Integration: turn persistence
# ---------------------------------------------------------------------------


class TestTurnPersistence:
    def test_turn_stores_user_and_assistant_with_pending_and_failed(
        self, client, session_id, llm
    ):
        llm.replies = [
            {
                "diffs": [
                    _modify("/flags/newCheckout/rollout", 25, 10),
                    _modify("/flags/missing/rollout", 1, 10),
                ],
                "explanation": "Set newCheckout rollout to 10.",
            }
        ]
        events = chat(client, session_id, "Set rollout to 10 for newCheckout")

        diff_events = [p["entry"] for e, p in events if e == "diff"]
        assert [d["status"] for d in diff_events] == ["pending"]

        done = complete_of(events)
        turns = get_history(client, session_id)
        assert [t["role"] for t in turns] == ["user", "assistant"]
        assert done["user_turn_id"] == turns[0]["id"]
        assert done["assistant_turn_id"] == turns[1]["id"]
        assert turns[0]["content"] == "Set rollout to 10 for newCheckout"
        assert statuses(turns) == ["pending", "failed"]
        assert turns[1]["diffs"][1]["failure_reason"]

    def test_no_diff_turn_is_still_stored(self, client, session_id, llm):
        llm.replies = [
            {"diffs": [], "explanation": "Which rollout — newCheckout or darkMode?"}
        ]
        chat(client, session_id, "change the rollout")

        turns = get_history(client, session_id)
        assert [t["role"] for t in turns] == ["user", "assistant"]
        assert turns[1]["content"].startswith("Which rollout")

    def test_quota_stop_stores_nothing(self, client, session_id, llm):
        llm.replies = [{"_quota": True}]
        events = chat(client, session_id, "anything")

        assert not any(e == "complete" for e, _ in events)
        assert get_history(client, session_id) == []

    def test_first_turn_sends_no_history_or_rules(self, client, session_id, llm):
        llm.replies = [{"diffs": [], "explanation": "ok"}]
        chat(client, session_id, "hello")

        assert llm.calls[0]["history"] == []
        assert "CONVERSATION HISTORY RULES" not in llm.calls[0]["system"]


# ---------------------------------------------------------------------------
# Integration: diff status lifecycle
# ---------------------------------------------------------------------------


class TestDiffStatusLifecycle:
    @pytest.fixture
    def three_pending(self, client, session_id, llm) -> list[str]:
        llm.replies = [
            {
                "diffs": [
                    _modify("/flags/newCheckout/rollout", 25, 10),
                    _modify("/flags/darkMode/rollout", 100, 10),
                    _modify("/flags/aiAssistant/rollout", 0, 10),
                ],
                "explanation": "Set rollout to 10 everywhere.",
            }
        ]
        chat(client, session_id, "rollout 10 for all")
        return [d["id"] for d in get_history(client, session_id)[1]["diffs"]]

    def test_accept_and_reject_one(self, client, session_id, three_pending):
        a, r, _ = three_pending
        acc = client.post(f"/api/sessions/{session_id}/diffs/{a}/accept")
        rej = client.post(f"/api/sessions/{session_id}/diffs/{r}/reject")
        assert acc.status_code == rej.status_code == 200

        body = rej.json()
        assert body["applied_diffs"] == [a]
        assert body["rejected_diffs"] == [r]
        assert body["working_json"]["flags"]["darkMode"]["rollout"] == 100  # reverted
        assert statuses(get_history(client, session_id)) == [
            "accepted",
            "rejected",
            "pending",
        ]

    def test_resolving_twice_is_409(self, client, session_id, three_pending):
        a = three_pending[0]
        client.post(f"/api/sessions/{session_id}/diffs/{a}/accept")
        assert (
            client.post(f"/api/sessions/{session_id}/diffs/{a}/accept").status_code
            == 409
        )
        assert (
            client.post(f"/api/sessions/{session_id}/diffs/{a}/reject").status_code
            == 409
        )

    def test_unknown_diff_is_404(self, client, session_id, three_pending):
        resp = client.post(f"/api/sessions/{session_id}/diffs/nope/accept")
        assert resp.status_code == 404

    def test_accept_all_marks_only_pending(self, client, session_id, three_pending):
        r = three_pending[1]
        client.post(f"/api/sessions/{session_id}/diffs/{r}/reject")
        body = client.post(f"/api/sessions/{session_id}/diffs/accept-all").json()

        assert statuses(body["conversation_history"]) == [
            "accepted",
            "rejected",
            "accepted",
        ]

    def test_reject_all_records_rejections(self, client, session_id, three_pending):
        body = client.post(f"/api/sessions/{session_id}/diffs/reject-all").json()

        assert statuses(body["conversation_history"]) == ["rejected"] * 3
        assert body["working_json"] == FLAGS


# ---------------------------------------------------------------------------
# Integration: history replay to the LLM (the "do it for all" use case)
# ---------------------------------------------------------------------------


class TestHistoryReplay:
    def test_follow_up_sees_previous_turn_with_statuses(self, client, session_id, llm):
        llm.replies = [
            {
                "diffs": [
                    _modify("/flags/newCheckout/rollout", 25, 10),
                    _modify("/flags/darkMode/rollout", 100, 10),
                ],
                "explanation": "Set rollout.",
            },
            {"diffs": [], "explanation": "ok"},
        ]
        chat(client, session_id, "Set rollout to 10 for newCheckout and darkMode")
        first, second = (d["id"] for d in get_history(client, session_id)[1]["diffs"])
        client.post(f"/api/sessions/{session_id}/diffs/{first}/accept")
        client.post(f"/api/sessions/{session_id}/diffs/{second}/reject")

        chat(client, session_id, "do the same for all such flags")

        call = llm.calls[1]
        assert "CONVERSATION HISTORY RULES" in call["system"]
        assert call["message"] == "do the same for all such flags"
        user_msg, assistant_msg = call["history"]
        assert user_msg == {
            "role": "user",
            "content": "Set rollout to 10 for newCheckout and darkMode",
        }
        assert assistant_msg["role"] == "assistant"
        replay = json.loads(assistant_msg["content"])
        assert replay["explanation"] == "Set rollout."
        assert [(d["path"], d["status"]) for d in replay["diffs"]] == [
            ("/flags/newCheckout/rollout", "accepted"),
            ("/flags/darkMode/rollout", "rejected"),
        ]
        # old_value carries the change's condition ("100 -> 10")
        assert [d["old_value"] for d in replay["diffs"]] == [25, 100]

    def test_status_change_after_turn_reflected_next_call(
        self, client, session_id, llm
    ):
        llm.replies = [
            {
                "diffs": [_modify("/flags/newCheckout/rollout", 25, 10)],
                "explanation": "a",
            },
            {"diffs": [], "explanation": "b"},
        ]
        chat(client, session_id, "first")
        chat(client, session_id, "second")  # diff still pending at this point

        replay = json.loads(llm.calls[1]["history"][1]["content"])
        assert replay["diffs"][0]["status"] == "pending"

    def test_history_disabled_by_setting(self, client, session_id, llm, monkeypatch):
        monkeypatch.setenv("CHAT_HISTORY_ENABLED", "false")
        get_settings.cache_clear()  # client fixture already loaded settings
        llm.replies = [
            {"diffs": [], "explanation": "a"},
            {"diffs": [], "explanation": "b"},
        ]
        chat(client, session_id, "first")
        chat(client, session_id, "second")

        assert llm.calls[1]["history"] == []


# ---------------------------------------------------------------------------
# Integration: production follow-up cases (2026-10-01/02 logs)
# ---------------------------------------------------------------------------

PLAYERS = {
    "gameplayer_list": [
        {"name": "A", "overall": 80, "parameters": [99, 70, 99]},
        {"name": "B", "overall": 81, "parameters": [99, 71, 55]},
    ]
}

DRAFT_FILES = {
    "files": [
        {"file": "roster_2026.json", "title": "Regular Season 2026"},
        {"file": "draft_2027_round1.json", "title": "Draft Season 2027 - Round 1"},
        {"file": "draft_2027_round2.json", "title": "Draft Season 2027 - Round 2"},
    ]
}


class TestProductionFollowUps:
    @pytest.fixture
    def doc_session(self, client):
        def make(doc):
            sid = client.post("/api/sessions", json={"name": "prod"}).json()["id"]
            client.post(
                "/api/json/upload",
                files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
            )
            return sid

        return make

    def test_turkish_all_players_follow_up_gets_prior_leaf_change(
        self, client, doc_session, llm
    ):
        """Prod: one player's parameter 99 -> 60, then 'Tum oyuncular icin
        degistir 99, olanlarin hepsi' returned 0 diffs (no context)."""
        sid = doc_session(PLAYERS)
        first = (
            '"parameters": [ 99, su oyuncularının parametreleri kisimlarını 60 yapımı'
        )
        follow = "Tum oyuncular icin degistir 99, olanlarin hepsi"
        llm.replies = [
            {
                "diffs": [_modify("/gameplayer_list/0/parameters/0", 99, 60)],
                "explanation": "Changed the first player's first parameter from 99 to 60.",
            },
            {
                "diffs": [
                    _modify("/gameplayer_list/0/parameters/2", 99, 60),
                    _modify("/gameplayer_list/1/parameters/0", 99, 60),
                ],
                "explanation": "Changed the remaining 99s to 60.",
            },
        ]
        chat(client, sid, first)
        client.post(f"/api/sessions/{sid}/diffs/accept-all")
        events = chat(client, sid, follow)

        call = llm.calls[1]
        assert call["message"] == follow
        assert call["history"][0]["content"] == first  # non-ASCII preserved
        replay = json.loads(call["history"][1]["content"])
        assert replay["diffs"] == [
            {
                "path": "/gameplayer_list/0/parameters/0",
                "operation": "modify",
                "old_value": 99,
                "new_value": 60,
                "status": "accepted",
            }
        ]
        assert "H5a" in call["system"]  # leaf-granularity generalisation rule

        merged = complete_of(events)["working_json"]
        assert [p["parameters"] for p in merged["gameplayer_list"]] == [
            [60, 70, 60],
            [60, 71, 55],
        ]

    def test_rephrased_delete_sees_pending_deletes(self, client, doc_session, llm):
        """Prod: 'delete every file that contains draft season 2027' asked
        twice; the rephrase must know what turn 1 already proposed."""
        sid = doc_session(DRAFT_FILES)
        llm.replies = [
            {
                "diffs": [
                    {
                        "path": "/files/2",
                        "operation": "delete",
                        "old_value": DRAFT_FILES["files"][2],
                        "new_value": None,
                    },
                    {
                        "path": "/files/1",
                        "operation": "delete",
                        "old_value": DRAFT_FILES["files"][1],
                        "new_value": None,
                    },
                ],
                "explanation": "Removed the Draft Season 2027 files.",
            },
            {"diffs": [], "explanation": "Already removed in the previous change."},
        ]
        events = chat(
            client,
            sid,
            "I want every file to be deleted that contains the draft season 2027",
        )
        assert complete_of(events)["working_json"]["files"] == DRAFT_FILES["files"][:1]

        chat(client, sid, "I want every file deleted that says draft season 2027")
        replay = json.loads(llm.calls[1]["history"][1]["content"])
        assert [(d["operation"], d["path"], d["status"]) for d in replay["diffs"]] == [
            ("delete", "/files/2", "pending"),
            ("delete", "/files/1", "pending"),
        ]
        assert replay["diffs"][1]["old_value"]["title"] == "Draft Season 2027 - Round 1"


# ---------------------------------------------------------------------------
# Integration: clear, version boundary, upload reset, restore
# ---------------------------------------------------------------------------


class TestThreadLifecycle:
    def test_clear_blocked_while_pending_then_allowed(self, client, session_id, llm):
        llm.replies = [
            {
                "diffs": [_modify("/flags/newCheckout/rollout", 25, 10)],
                "explanation": "a",
            }
        ]
        chat(client, session_id, "change")

        assert client.delete(f"/api/sessions/{session_id}/chat").status_code == 409
        client.post(f"/api/sessions/{session_id}/diffs/accept-all")
        assert client.delete(f"/api/sessions/{session_id}/chat").status_code == 204
        assert get_history(client, session_id) == []

    def test_clear_unknown_session_404(self, client):
        assert client.delete("/api/sessions/nope/chat").status_code == 404

    def test_version_select_adds_boundary_and_rejects_pending(
        self, client, session_id, llm
    ):
        llm.replies = [
            {
                "diffs": [_modify("/flags/newCheckout/rollout", 25, 10)],
                "explanation": "a",
            },
            {"diffs": [], "explanation": "b"},
        ]
        version = client.post(
            f"/api/sessions/{session_id}/versions",
            json={"label": "base", "json_data": FLAGS},
        ).json()
        chat(client, session_id, "change")

        body = client.post(
            f"/api/sessions/{session_id}/versions/select",
            json={"versionId": version["id"]},
        ).json()
        turns = body["conversation_history"]
        assert [t["kind"] for t in turns] == ["message", "message", "boundary"]
        assert "base" in turns[-1]["content"]
        assert statuses(turns) == ["rejected"]

        chat(client, session_id, "after switch")
        assert llm.calls[1]["history"] == []  # nothing replayed past the boundary

    def test_upload_new_json_clears_thread(self, client, session_id, llm):
        llm.replies = [{"diffs": [], "explanation": "a"}]
        chat(client, session_id, "hello")
        client.post(
            "/api/json/upload",
            files={
                "json_body": (None, json.dumps({"x": 1})),
                "session_id": (None, session_id),
            },
        )
        assert get_history(client, session_id) == []

    def test_restore_carries_thread_and_statuses(self, client, llm):
        sid = client.post("/api/sessions", json={"name": "restored"}).json()["id"]
        cached = [
            {"id": "u1", "role": "user", "content": "set it"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "done",
                "diffs": [
                    {
                        "id": "d1",
                        **_modify("/flags/newCheckout/rollout", 25, 10),
                        "status": "accepted",
                    }
                ],
            },
        ]
        resp = client.post(
            f"/api/sessions/{sid}/versions/restore",
            json={
                "versions": [],
                "working_json": FLAGS,
                "conversation_history": cached,
            },
        )
        assert resp.status_code == 200

        turns = get_history(client, sid)
        assert [t["id"] for t in turns] == ["u1", "a1"]
        assert statuses(turns) == ["accepted"]

        llm.replies = [{"diffs": [], "explanation": "b"}]
        chat(client, sid, "next")
        assert llm.calls[0]["history"][0]["content"] == "set it"


# ---------------------------------------------------------------------------
# Unit: replay shaping in chat_history_service
# ---------------------------------------------------------------------------


def _session_with_pairs(n: int, diffs_per_turn: int = 1, value: Any = 1):
    session: dict[str, Any] = {"id": "s", "conversation_history": []}
    for i in range(n):
        diffs = [
            {
                "id": f"d{i}-{j}",
                **_modify(f"/k{i}/{j}", 0, value),
                "status": "accepted",
            }
            for j in range(diffs_per_turn)
        ]
        history.append_turns(
            session,
            history.make_turn("user", f"msg {i}"),
            history.make_turn("assistant", f"exp {i}", diffs=diffs),
        )
    return session


class TestReplayShaping:
    def test_turn_cap_keeps_most_recent_pairs(self, monkeypatch):
        monkeypatch.setenv("CHAT_HISTORY_MAX_TURNS", "2")
        msgs = history.build_history_messages(_session_with_pairs(5))
        assert [m["content"] for m in msgs if m["role"] == "user"] == ["msg 3", "msg 4"]

    def test_token_budget_drops_oldest_whole_pairs(self, monkeypatch):
        monkeypatch.setenv("CHAT_HISTORY_MAX_TOKENS", "120")
        msgs = history.build_history_messages(_session_with_pairs(6))
        assert msgs, "at least the newest pair should fit"
        assert len(msgs) % 2 == 0  # never a user turn without its reply
        assert msgs[-2]["content"] == "msg 5"

    def test_large_values_truncated_and_diffs_capped(self, monkeypatch):
        monkeypatch.setenv("CHAT_HISTORY_MAX_DIFFS_PER_TURN", "2")
        session = _session_with_pairs(1, diffs_per_turn=5, value="x" * 1000)
        replay = json.loads(history.build_history_messages(session)[1]["content"])

        assert len(replay["diffs"]) == 3  # 2 diffs + summary note
        assert replay["diffs"][0]["new_value"].endswith("…(truncated)")
        assert "3 more diffs" in replay["diffs"][-1]["note"]

    def test_unpaired_user_turn_not_replayed(self):
        session = _session_with_pairs(1)
        history.append_turns(session, history.make_turn("user", "dangling"))
        contents = [m["content"] for m in history.build_history_messages(session)]
        assert "dangling" not in contents

    def test_stored_turn_cap_prunes_oldest(self, monkeypatch):
        monkeypatch.setenv("CHAT_HISTORY_MAX_STORED_TURNS", "4")
        session = _session_with_pairs(5)
        assert [t["content"] for t in session["conversation_history"]] == [
            "msg 3",
            "exp 3",
            "msg 4",
            "exp 4",
        ]

    def test_fit_to_context_drops_history_before_system(self, monkeypatch):
        monkeypatch.setattr(
            history.litellm, "get_model_info", lambda m: {"max_input_tokens": 50}
        )
        monkeypatch.setattr(
            history,
            "_count_tokens",
            lambda model, msgs: sum(len(m["content"]) for m in msgs),
        )
        hist = [
            {"role": "user", "content": "u" * 20},
            {"role": "assistant", "content": "a" * 20},
        ]
        msgs = history.fit_to_context("m", "s" * 10, hist, "q", reserve_output=0)
        assert [m["role"] for m in msgs] == ["system", "user"]  # history dropped

    def test_fit_to_context_unknown_model_keeps_history(self, monkeypatch):
        def boom(model):
            raise Exception("unknown model")

        monkeypatch.setattr(history.litellm, "get_model_info", boom)
        hist = [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}]
        msgs = history.fit_to_context("m", "s", hist, "q", reserve_output=0)
        assert len(msgs) == 4
