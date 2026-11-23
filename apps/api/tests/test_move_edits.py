"""move / rename ops → add + delete diffs (move_edits.py), unit and through
the real /api/chat SSE path (LLM stubbed at GatewayService.invoke)."""

from __future__ import annotations

import json

import pytest

from src.json_ai_studio.diff_utils import DiffUtils
from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.move_edits import expand_moves
from tests.test_chat_history import FakeLLM, chat, client, complete_of  # noqa: F401

SKINS = {
    "skins": [
        {"localization_name": f"Skin {i}", "texture": f"a{i}.png", "type": "free"}
        for i in range(3)
    ]
}


def run(diffs, doc, bulk=None):
    out, ops, notes = expand_moves(diffs, bulk or [], doc, 1000)
    result, applied, failed = DiffUtils.apply_all_verbose(out, doc)
    return result, out, ops, notes, failed


def test_move_scalar_and_rename():
    doc = {"user": {"fullname": "Ada", "age": 3}}
    result, out, _, notes, failed = run(
        [
            {"operation": "rename", "path": "/user/fullname", "new_key": "name"},
            {"operation": "move", "from": "/user/age", "path": "/meta/age"},
        ],
        doc,
    )
    assert not notes and not failed
    assert result == {"user": {"name": "Ada"}, "meta": {"age": 3}}
    assert {d["operation"] for d in out} == {"add", "delete"}


def test_rename_accepts_new_value_as_key_name():
    doc = {"a": {"x": 1}}
    result, *_ = run([{"operation": "rename", "path": "/a/x", "new_value": "y"}], doc)
    assert result == {"a": {"y": 1}}


def test_wildcard_moves_merge_into_one_created_parent():
    result, out, _, notes, failed = run(
        [
            {
                "operation": "move",
                "from": "/skins/*/localization_name",
                "path": "/skins/*/id",
            },
            {
                "operation": "move",
                "from": "/skins/*/texture",
                "path": "/skins/*/textures/body",
            },
            {
                "operation": "move",
                "from": "/skins/*/type",
                "path": "/skins/*/textures/kind",
            },
        ],
        SKINS,
    )
    assert not notes and not failed
    assert result["skins"][1] == {
        "id": "Skin 1",
        "textures": {"body": "a1.png", "kind": "free"},
    }
    # one add per created textures object, not one per moved field
    adds = [d["path"] for d in out if d["operation"] == "add"]
    assert adds.count("/skins/1/textures") == 1


def test_wildcard_move_in_bulk_with_where():
    doc = {"items": [{"k": "a", "v": 1}, {"k": "b", "v": 2}]}
    result, _, ops, notes, failed = run(
        [],
        doc,
        bulk=[
            {
                "operation": "move",
                "from": "/items/*/v",
                "path": "/items/*/value",
                "where": {"k": "b"},
            },
            {"path": "/items/*/k", "operation": "delete"},
        ],
    )
    assert ops == [{"path": "/items/*/k", "operation": "delete"}]
    assert result == {"items": [{"k": "a", "v": 1}, {"k": "b", "value": 2}]}


def test_move_array_element_between_lists():
    doc = {"todo": ["a", "b", "c"], "done": ["x"]}
    result, *_ = run([{"operation": "move", "from": "/todo/1", "path": "/done/-"}], doc)
    assert result == {"todo": ["a", "c"], "done": ["x", "b"]}


@pytest.mark.parametrize(
    "entry,reason",
    [
        ({"operation": "move", "from": "/a", "path": "/b"}, "already exists"),
        ({"operation": "move", "from": "/nope", "path": "/c"}, "does not exist"),
        ({"operation": "move", "from": "/a", "path": "/a/x"}, "into itself"),
        ({"operation": "move", "from": "/a", "path": "/s/x"}, "not an object"),
        ({"operation": "move", "from": "/x/*", "path": "/y"}, "same number"),
        ({"operation": "rename", "path": "/a"}, "new_key"),
    ],
)
def test_refusals_leave_document_untouched(entry, reason):
    doc = {"a": {"k": 1}, "b": 2, "s": "text"}
    result, out, _, notes, _ = run([entry], doc)
    assert result == doc and not out
    assert len(notes) == 1 and reason in notes[0]


def test_target_already_equal_only_deletes_source():
    doc = {"a": 1, "b": 1}
    result, *_ = run([{"operation": "move", "from": "/a", "path": "/b"}], doc)
    assert result == {"b": 1}


def test_model_own_diff_on_same_path_wins():
    doc = {"a": 1}
    diffs = [
        {"operation": "move", "from": "/a", "path": "/b"},
        {"operation": "delete", "path": "/a", "old_value": 1, "new_value": None},
    ]
    result, out, _, _, failed = run(diffs, doc)
    assert not failed and result == {"b": 1}
    assert [d["operation"] for d in out].count("delete") == 1


# --- through /api/chat --------------------------------------------------------


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


def test_chat_restructure_with_moves_then_accept_and_reject(client, llm):
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(SKINS)), "session_id": (None, sid)},
    )
    llm.replies = [
        {
            "diffs": [
                {
                    "path": "/skins/*/id",
                    "operation": "move",
                    "from": "/skins/*/localization_name",
                },
                {
                    "path": "/skins/*/textures/body",
                    "operation": "move",
                    "from": "/skins/*/texture",
                },
            ],
            "bulk": [{"path": "/skins/*/type", "operation": "delete"}],
            "explanation": "restructured",
        }
    ]
    done = complete_of(chat(client, sid, "restructure"))
    want = [{"id": f"Skin {i}", "textures": {"body": f"a{i}.png"}} for i in range(3)]
    assert done["working_json"]["skins"] == want

    accepted = client.post(f"/api/sessions/{sid}/diffs/accept-all").json()
    assert accepted["baseline_json"]["skins"] == want


def test_chat_reject_all_moves_restores_document(client, llm):
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(SKINS)), "session_id": (None, sid)},
    )
    llm.replies = [
        {
            "diffs": [
                {
                    "path": "/skins/*/textures/body",
                    "operation": "move",
                    "from": "/skins/*/texture",
                }
            ],
            "explanation": "nested",
        }
    ]
    complete_of(chat(client, sid, "nest textures"))
    rejected = client.post(f"/api/sessions/{sid}/diffs/reject-all").json()
    assert rejected["working_json"] == SKINS
