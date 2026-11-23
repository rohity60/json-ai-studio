"""{"$from"} copies in plain and wildcard diffs through the real /api/chat
SSE path. LLM stubbed at GatewayService.invoke.

Prod 2026-11-22: 449 skins restructured with modifies whose new_value held
{"$from": "localization_name"} — written into the document verbatim. Live
evals 2026-11-23 (nvidia nemotron, gemma4) showed three model shapes:
whole-element modifies per index, per-field adds, and one 'modify
/skins/*' wildcard sent as a plain diff.
"""

from __future__ import annotations

import json

import pytest

from tests.test_chat_history import FakeLLM, chat, client, complete_of  # noqa: F401
from src.json_ai_studio.bulk_edits import BulkEditError, expand_bulk
from src.json_ai_studio.bulk_edits import split_wildcard_diffs
from src.json_ai_studio.gateway import GatewayService

SKINS = [
    {"localization_name": f"Skin {i}", "texture": f"a{i}.png", "type": "free"}
    for i in range(3)
]
LAYOUT = {
    "id": {"$from": "localization_name"},
    "textures": {"body": {"$from": "texture"}},
    "model": "steve",
}
WANT = [
    {"id": f"Skin {i}", "textures": {"body": f"a{i}.png"}, "model": "steve"}
    for i in range(3)
]


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


def _session(client) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    resp = client.post(
        "/api/json/upload",
        files={
            "json_body": (None, json.dumps({"skins": SKINS})),
            "session_id": (None, sid),
        },
    )
    assert resp.status_code == 200
    return sid


SHAPES = {
    "per_index_modify": [
        {
            "path": f"/skins/{i}",
            "operation": "modify",
            "old_value": SKINS[i],
            "new_value": LAYOUT,
        }
        for i in range(3)
    ],
    "wildcard_plain_diff": [
        {
            "path": "/skins/*",
            "operation": "modify",
            "old_value": None,
            "new_value": LAYOUT,
        }
    ],
}


@pytest.mark.parametrize("shape", list(SHAPES))
def test_from_markers_resolved_per_skin(client, llm, shape):
    sid = _session(client)
    llm.replies = [{"diffs": SHAPES[shape], "explanation": "restructured"}]
    done = complete_of(chat(client, sid, "restructure skins"))
    assert done["working_json"]["skins"] == WANT
    assert "$from" not in json.dumps(done["working_json"])

    turn = client.get(f"/api/sessions/{sid}").json()["conversation_history"][-1]
    assert [d["status"] for d in turn["diffs"]] == ["pending"] * 3
    assert "$from" not in json.dumps(turn["diffs"])

    accepted = client.post(f"/api/sessions/{sid}/diffs/accept-all").json()
    assert accepted["baseline_json"]["skins"] == WANT


def test_wildcard_collapsing_each_skin_into_a_field_is_refused(client, llm):
    sid = _session(client)
    llm.replies = [
        {
            "diffs": [
                {
                    "path": "/skins/*",
                    "operation": "modify",
                    "new_value": {"$from": "localization_name"},
                }
            ],
            "explanation": "renamed",
        }
    ]
    done = complete_of(chat(client, sid, "rename localization_name to id"))
    assert done["working_json"]["skins"] == SKINS


def test_split_wildcard_diffs_keeps_append_and_plain():
    diffs = [
        {"path": "/skins/0/id", "operation": "modify", "new_value": 1},
        {"path": "/skins/*", "operation": "add", "new_value": {}},
        {"path": "/skins/*/id", "operation": "add", "new_value": 2},
        {"path": "/skins/*", "operation": "modify", "new_value": {}},
    ]
    plain, ops = split_wildcard_diffs(diffs)
    assert [d["path"] for d in plain] == ["/skins/0/id", "/skins/*"]
    assert [o["path"] for o in ops] == ["/skins/*/id", "/skins/*"]


def test_bulk_from_copy_into_leaf_still_allowed():
    doc = {"items": [{"a": 1, "b": {"x": 1}}]}
    diffs = expand_bulk(
        {"path": "/items/*/a", "operation": "modify", "new_value": {"$from": "b"}},
        doc,
        100,
    )
    assert diffs[0]["new_value"] == {"x": 1}


def test_bulk_from_collapsing_element_refused():
    doc = {"items": [{"a": 1}]}
    with pytest.raises(BulkEditError):
        expand_bulk(
            {"path": "/items/*", "operation": "modify", "new_value": {"$from": "a"}},
            doc,
            100,
        )
