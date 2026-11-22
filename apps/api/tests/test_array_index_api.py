"""Several ops on one array through the real /api/chat SSE path.

Regression for prod session 5a829e00 (2026-11-21): 4 role adds numbered
50..53 on a 51-item list — 2 failed "out of range" and one landed before
the last existing role. Indices are snapshot indices (prompt rule 4);
the server orders them (diff_utils._apply_order) and folds sequential
append runs (_normalise_append_runs). LLM stubbed at GatewayService.invoke.
"""

from __future__ import annotations

import json

import pytest

from tests.test_chat_history import FakeLLM, chat, client, complete_of  # noqa: F401
from src.json_ai_studio.gateway import GatewayService


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


def _add(path, n):
    return {"path": path, "operation": "add", "old_value": None, "new_value": {"n": n}}


def _del(path, n):
    return {
        "path": path,
        "operation": "delete",
        "old_value": {"n": n},
        "new_value": None,
    }


def _session(client, items) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    doc = {"steps": [{"n": n} for n in items]}
    resp = client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
    )
    assert resp.status_code == 200
    return sid


def _names(doc) -> str:
    return "".join(s["n"] for s in doc["steps"])


ROLES = [f"r{i}" for i in range(51)]

CASES = [
    (
        "prod_four_roles_off_by_one",
        ROLES,
        [_add(f"/steps/{50 + i}", n) for i, n in enumerate("WXYZ")],
        "".join(ROLES) + "WXYZ",
    ),
    (
        "two_inserts_same_gap",
        list("ABCD"),
        [_add("/steps/1", "X"), _add("/steps/1", "Y")],
        "AXYBCD",
    ),
    (
        "insert_and_delete",
        list("ABCD"),
        [_add("/steps/1", "X"), _del("/steps/2", "C")],
        "AXBD",
    ),
    (
        "delete_two",
        list("ABCD"),
        [_del("/steps/0", "A"), _del("/steps/2", "C")],
        "BD",
    ),
]


@pytest.mark.parametrize(
    "items,diffs,want", [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
def test_chat_applies_all_and_streams_in_model_order(client, llm, items, diffs, want):
    sid = _session(client, items)
    llm.replies = [{"diffs": diffs, "explanation": "done"}]
    events = chat(client, sid, "edit the steps")

    streamed = [p["entry"] for e, p in events if e == "diff"]
    assert [d["new_value"] for d in streamed] == [d["new_value"] for d in diffs]
    done = complete_of(events)
    assert _names(done["working_json"]) == want
    assert "Skipped" not in done["explanation"]

    turn = client.get(f"/api/sessions/{sid}").json()["conversation_history"][-1]
    assert [d["status"] for d in turn["diffs"]] == ["pending"] * len(diffs)

    accepted = client.post(f"/api/sessions/{sid}/diffs/accept-all").json()
    assert _names(accepted["baseline_json"]) == want


# ---------------------------------------------------------------------------
# Reject / accept of appends one by one (2026-11-23: rejecting an append
# popped the LAST item, so the preview kept the rejected one and a later
# accept-all saved it).
# ---------------------------------------------------------------------------

APPENDS = [_add("/steps/-", n) for n in "XYZ"]


def _ids(events) -> dict[str, str]:
    return {
        p["entry"]["new_value"]["n"]: p["entry"]["id"] for e, p in events if e == "diff"
    }


def _state(client, sid) -> tuple[str, str]:
    s = client.get(f"/api/sessions/{sid}").json()
    return _names(s["baseline_json"]), _names(s["working_json"])


@pytest.mark.parametrize(
    "clicks,want",
    [
        ([("Y", "reject"), ("X", "accept"), ("Z", "accept")], "ABCXZ"),
        ([("X", "reject"), ("Y", "accept"), ("Z", "accept")], "ABCYZ"),
        ([("Z", "reject"), ("X", "reject"), ("Y", "accept")], "ABCY"),
    ],
    ids=["reject_middle", "reject_first", "reject_two"],
)
def test_appends_decided_one_by_one(client, llm, clicks, want):
    sid = _session(client, "ABC")
    llm.replies = [{"diffs": APPENDS, "explanation": "added"}]
    events = chat(client, sid, "add X Y Z")
    entries = [p["entry"] for e, p in events if e == "diff"]
    assert [d["path"] for d in entries] == ["/steps/3", "/steps/4", "/steps/5"]
    ids = _ids(events)
    for name, verb in clicks:
        resp = client.post(f"/api/sessions/{sid}/diffs/{ids[name]}/{verb}")
        assert resp.status_code == 200, resp.text
    assert _state(client, sid) == (want, want)


def test_reject_then_accept_all_keeps_rejection(client, llm):
    sid = _session(client, "ABC")
    llm.replies = [{"diffs": APPENDS, "explanation": "added"}]
    ids = _ids(chat(client, sid, "add X Y Z"))
    client.post(f"/api/sessions/{sid}/diffs/{ids['Y']}/reject")
    out = client.post(f"/api/sessions/{sid}/diffs/accept-all").json()
    assert _names(out["baseline_json"]) == "ABCXZ"


def test_reject_append_from_earlier_turn(client, llm):
    sid = _session(client, "ABC")
    llm.replies = [
        {"diffs": [_add("/steps/-", "X")], "explanation": "x"},
        {"diffs": [_add("/steps/-", "Y")], "explanation": "y"},
    ]
    x = _ids(chat(client, sid, "add X"))["X"]
    y = _ids(chat(client, sid, "add Y"))["Y"]
    client.post(f"/api/sessions/{sid}/diffs/{x}/reject")
    client.post(f"/api/sessions/{sid}/diffs/{y}/accept")
    assert _state(client, sid) == ("ABCY", "ABCY")


def test_history_replays_concrete_append_path(client, llm):
    sid = _session(client, "ABC")
    llm.replies = [
        {"diffs": [_add("/steps/-", "X")], "explanation": "x"},
        {"diffs": [], "explanation": "ok"},
    ]
    chat(client, sid, "add X")
    chat(client, sid, "rename it")
    replay = llm.calls[-1]["history"][-1]["content"]
    assert '"/steps/3"' in replay and "/steps/-" not in replay
