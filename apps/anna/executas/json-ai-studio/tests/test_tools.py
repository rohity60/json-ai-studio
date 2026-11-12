"""Tool handlers against an in-memory Anna host: the real engine (gateway,
planner, diff services) runs; only the host side is faked."""

from __future__ import annotations

import json

from jstudio import tools
from jstudio.aps_store import INLINE_MAX_BYTES
from jstudio.rpc import HostError

DOC = {"service": {"timeout": 30, "retryCount": 3}}
RAISE_TIMEOUT = {
    "diffs": [
        {
            "path": "/service/timeout",
            "operation": "modify",
            "old_value": 30,
            "new_value": 60,
        }
    ],
    "explanation": "Raised the timeout.",
}


async def ok(tool: str, **args):
    result = await tools.run(tool, args)
    assert result["success"], result
    return result["data"]


async def test_edit_review_and_version_round_trip(anna):
    sid = (await ok("create_doc", json=DOC, name="svc"))["session_id"]

    anna.replies.append(RAISE_TIMEOUT)
    turn = await ok("chat_turn", session_id=sid, message="set timeout to 60")
    events = {e["event"]: e["data"] for e in turn["events"]}
    assert "error" not in events, turn
    assert events["diff"]["entry"]["path"] == "/service/timeout"
    assert events["complete"]["explanation"] == "Raised the timeout."

    await ok("accept_all", session_id=sid)
    version = await ok("save_version", session_id=sid, label="after timeout")
    assert version["label"] == "after timeout"

    doc = await ok("get_doc", session_id=sid)
    assert doc["working_json"]["service"]["timeout"] == 60
    assert len(doc["versions"]) == 1
    assert [d["id"] for d in (await ok("list_docs"))["docs"]] == [sid]


async def test_sampling_request_follows_anna_limits(anna):
    sid = (await ok("create_doc", json=DOC))["session_id"]
    anna.replies.append(RAISE_TIMEOUT)
    await ok("chat_turn", session_id=sid, message="set timeout to 60")

    (call,) = anna.sampling_calls
    assert call["thinking"] is False  # always explicit
    assert call["maxTokens"] <= 8192
    assert call["includeContext"] == "none"
    assert call["systemPrompt"]  # system prompt carried separately
    assert {m["role"] for m in call["messages"]} <= {"user", "assistant"}
    assert call["messages"][-1]["content"]["text"].endswith("set timeout to 60")


async def test_large_document_goes_to_object_storage(anna):
    big = {"items": [{"id": i, "note": "x" * 100} for i in range(1000)]}
    assert len(json.dumps(big)) > INLINE_MAX_BYTES
    sid = (await ok("create_doc", json=big))["session_id"]

    assert anna.kv[f"sessions/{sid}"]["file"] == f"sessions/{sid}.json"
    assert f"sessions/{sid}.json" in anna.objects
    doc = await ok("get_doc", session_id=sid)
    assert doc["working_json"] == big


async def test_out_of_credits_is_explained(anna):
    sid = (await ok("create_doc", json=DOC))["session_id"]
    anna.replies.append(HostError(-32002, "SAMPLING_QUOTA_EXCEEDED"))
    turn = await ok("chat_turn", session_id=sid, message="set timeout to 60")

    events = [e["event"] for e in turn["events"]]
    assert "diff" not in events
    host_error = next(e for e in turn["events"] if e["event"] == "host_error")
    assert host_error["data"]["message"] == tools.OUT_OF_CREDITS
    doc = await ok("get_doc", session_id=sid)
    assert doc["working_json"] == DOC  # nothing changed


async def test_bad_calls_fail_cleanly(anna):
    assert (await tools.run("nope", {}))["success"] is False
    missing = await tools.run("get_doc", {})
    assert missing == {"success": False, "error": "'session_id' is required"}
    unknown = await tools.run("get_doc", {"session_id": "does-not-exist"})
    assert unknown == {"success": False, "error": "404: Session not found"}
    bad = await tools.run("create_doc", {"json": "{not json"})
    assert bad["success"] is False and "Not valid JSON" in bad["error"]


async def test_delete_removes_document(anna):
    sid = (await ok("create_doc", json=DOC))["session_id"]
    assert (await ok("delete_doc", session_id=sid))["deleted"] is True
    assert (await ok("list_docs"))["docs"] == []
    assert (await tools.run("get_doc", {"session_id": sid}))["success"] is False


async def test_web_client_calls_have_equivalents(anna):
    """create_session / upload_json / restore_versions mirror the HTTP API
    the shared React session code is written against."""
    session = await ok("create_session", name="Restored")
    assert session["working_json"] == {}

    up = await ok("upload_json", json=DOC, session_id=session["id"])
    assert up["session_id"] == session["id"] and up["after"] == DOC

    fresh = await ok("create_session")
    restored = await ok(
        "restore_versions",
        session_id=fresh["id"],
        payload={
            "versions": [
                {
                    "id": "v1",
                    "parent_id": None,
                    "json_data": DOC,
                    "label": "first",
                    "created_at": "2026-11-01T00:00:00+00:00",
                }
            ],
            "working_json": DOC,
            "active_version_id": "v1",
        },
    )
    assert restored["working_json"] == DOC
    assert [v["id"] for v in restored["versions"]] == ["v1"]
    again = await tools.run(
        "restore_versions", {"session_id": fresh["id"], "payload": {"versions": []}}
    )
    assert again["success"] is False and again["error"].startswith("409: ")
