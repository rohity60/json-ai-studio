"""Stamp guard (guards.py): distinct records must not all become one copy.

Unit tests plus the real /api/chat SSE path (LLM stubbed at
GatewayService.invoke). Prod 2026-11-22 / live evals 2026-11-23: every one
of 449 skins got the example's "id": "Steve".
"""

from __future__ import annotations

import json

import pytest

from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.guards import (
    KEEP_OPTION,
    SAME_OPTION,
    find_stamped_arrays,
    wants_identical,
)
from tests.test_chat_history import FakeLLM, chat, client, complete_of  # noqa: F401

N = 6
SKINS = [{"name": f"Skin {i}", "texture": f"a{i}.png"} for i in range(N)]
STEVE = {"id": "Steve", "textures": {"body": "steve.png"}}


def test_whole_records_stamped():
    hits = find_stamped_arrays({"skins": SKINS}, {"skins": [STEVE] * N})
    assert [h["path"] for h in hits] == ["/skins"]
    assert hits[0]["count"] == N


def test_bulk_field_edit_is_not_a_stamp():
    after = [{**s, "texture": "same.png"} for s in SKINS]
    assert find_stamped_arrays({"skins": SKINS}, {"skins": after}) == []


def test_small_arrays_and_scalar_lists_ignored():
    assert find_stamped_arrays({"s": SKINS[:4]}, {"s": [STEVE] * 4}) == []
    tags = [f"t{i}" for i in range(10)]
    assert find_stamped_arrays({"t": tags}, {"t": ["x"] * 10}) == []


def test_records_already_identical_are_not_flagged():
    same = [{"a": 1}] * N
    assert find_stamped_arrays({"s": same}, {"s": [{"a": 2}] * N}) == []


def test_nested_array_path():
    before = {"packs": [{"skins": SKINS}]}
    after = {"packs": [{"skins": [STEVE] * N}]}
    assert [h["path"] for h in find_stamped_arrays(before, after)] == ["/packs/0/skins"]


@pytest.mark.parametrize(
    "msg,want",
    [
        (SAME_OPTION, True),
        ("make all skins identical", True),
        ("use the same values for all skins", True),
        (KEEP_OPTION, False),
        ("match this layout exactly", False),
    ],
)
def test_override_phrases(msg, want):
    assert wants_identical(msg) is want


# --- through /api/chat --------------------------------------------------------


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake.invoke))
    return fake


def _session(client) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    doc = {"pack": {"name": "old"}, "skins": SKINS}
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(doc)), "session_id": (None, sid)},
    )
    return sid


STAMP_REPLY = {
    "diffs": [
        {
            "path": f"/skins/{i}",
            "operation": "modify",
            "old_value": s,
            "new_value": STEVE,
        }
        for i, s in enumerate(SKINS)
    ]
    + [
        {
            "path": "/pack/name",
            "operation": "modify",
            "old_value": "old",
            "new_value": "My Pack",
        }
    ],
    "explanation": "Set every skin to the example layout.",
}


def test_chat_holds_stamp_keeps_other_diffs_and_asks(client, llm):
    sid = _session(client)
    llm.replies = [STAMP_REPLY]
    events = chat(client, sid, "change the skins to match this layout exactly")
    done = complete_of(events)
    assert done["working_json"]["skins"] == SKINS  # untouched
    assert done["working_json"]["pack"] == {"name": "My Pack"}  # rest applied
    assert "Not applied" in done["explanation"] and "'Skin 0'" in done["explanation"]
    assert "Set every skin" not in done["explanation"]
    assert done["question"]["options"] == [KEEP_OPTION, SAME_OPTION]

    turn = client.get(f"/api/sessions/{sid}").json()["conversation_history"][-1]
    assert [d["path"] for d in turn["diffs"]] == ["/pack/name"]
    assert turn.get("question", {}).get("options") == [KEEP_OPTION, SAME_OPTION]


def test_chat_explicit_identical_request_is_applied(client, llm):
    sid = _session(client)
    llm.replies = [STAMP_REPLY]
    done = complete_of(chat(client, sid, SAME_OPTION))
    assert done["working_json"]["skins"] == [STEVE] * N
    assert "question" not in done


# --- example-value guard ------------------------------------------------------

from src.json_ai_studio.guards import (  # noqa: E402
    EXAMPLE_KEEP_OPTION,
    EXAMPLE_USE_OPTION,
    find_example_stamps,
    wants_example_values,
)

GEO = [{"name": f"Skin {i}", "geometry": f"geometry.a{i}"} for i in range(N)]
LAYOUT_MSG = 'match this layout exactly: {"skins": [{"id": "Steve", "geometry": "models/steve.obj"}]}'


def _geo_after(value="models/steve.obj"):
    return [{"id": s["name"], "geometry": value} for s in GEO]


def test_example_value_stamp_detected():
    hits = find_example_stamps({"skins": GEO}, {"skins": _geo_after()}, LAYOUT_MSG)
    assert [(h["path"], h["field"], h["value"]) for h in hits] == [
        ("/skins", "geometry", "models/steve.obj")
    ]


@pytest.mark.parametrize(
    "msg",
    [
        "set geometry to models/steve.obj for every skin",  # no JSON example
        'use this: {"x": 1}',  # value not in the example
    ],
)
def test_example_value_stamp_needs_value_inside_json_example(msg):
    assert find_example_stamps({"skins": GEO}, {"skins": _geo_after()}, msg) == []


def test_example_value_new_field_is_fine():
    before = [{"name": f"S{i}"} for i in range(N)]
    after = [{"id": f"S{i}", "model": "steve"} for i in range(N)]
    msg = 'like {"skins": [{"id": "Steve", "model": "steve"}]}'
    assert find_example_stamps({"s": before}, {"s": after}, msg) == []


def test_example_value_override_phrase():
    assert wants_example_values(EXAMPLE_USE_OPTION)
    assert not wants_example_values(EXAMPLE_KEEP_OPTION)
    assert not wants_example_values(LAYOUT_MSG)


def _geo_session(client) -> str:
    sid = client.post("/api/sessions", json={"name": "t"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={
            "json_body": (None, json.dumps({"skins": GEO})),
            "session_id": (None, sid),
        },
    )
    return sid


GEO_REPLY = {
    "diffs": [
        {"path": "/pack", "operation": "add", "new_value": {"id": "P"}},
        *[
            {
                "path": f"/skins/{i}",
                "operation": "modify",
                "old_value": s,
                "new_value": {"id": s["name"], "geometry": "models/steve.obj"},
            }
            for i, s in enumerate(GEO)
        ],
    ],
    "explanation": "Reshaped every skin.",
}


def test_chat_example_value_guard_asks(client, llm):
    sid = _geo_session(client)
    llm.replies = [GEO_REPLY]
    done = complete_of(chat(client, sid, LAYOUT_MSG))
    assert done["working_json"]["skins"] == GEO
    assert done["working_json"]["pack"] == {"id": "P"}
    assert "geometry" in done["explanation"] and '"geometry.a0"' in done["explanation"]
    assert done["question"]["options"] == [EXAMPLE_KEEP_OPTION, EXAMPLE_USE_OPTION]


def test_chat_example_value_applied_when_user_chooses_it(client, llm):
    sid = _geo_session(client)
    llm.replies = [GEO_REPLY]
    done = complete_of(chat(client, sid, EXAMPLE_USE_OPTION + " " + LAYOUT_MSG))
    assert done["working_json"]["skins"] == _geo_after()


def test_example_stamp_skips_field_missing_in_some_elements():
    # Regression (2026-11-23): an element without the field crashed the
    # check (sentinel passed to json.dumps).
    from src.json_ai_studio.guards import find_example_stamps

    before = {"s": [{"g": f"g{i}"} for i in range(6)]}
    after = {"s": [{"g": "x.obj"} for _ in range(5)] + [{"other": 1}]}
    assert find_example_stamps(before, after, 'like {"g": "x.obj"}') == []
