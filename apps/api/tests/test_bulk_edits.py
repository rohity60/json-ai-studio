"""Bulk edit tests: pattern expansion (unit) + chat pipeline (integration).

Bulk ops let the model change many elements — including ones it cannot see
when the document is too large to inline (skeleton prompt) — by emitting a
pattern the server expands against the full JSON. Production case
(2026-10-11, gita.json, 701 records): "apply the same change to all records"
/ "first 100" / "first 20" were refused because only records[0] was visible.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.json_ai_studio.bulk_edits import expand_all, expand_bulk, extract_bulk
from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.settings import get_settings


def _records(n: int = 30) -> list[dict]:
    # slokNumber restarts per chapter, like the real Bhagavad Gita export.
    out = []
    for i in range(n):
        ch = 1 if i < 12 else 2
        out.append(
            {
                "sectionId": f"bhagavad_gita_ch_{ch}",
                "slokNumber": i + 1 if ch == 1 else i - 11,
                "chapterName": "Arjuna Visada Yoga" if ch == 1 else "Sankhya Yoga",
                "status": "PENDING",
            }
        )
    return out


DOC = {"source": "gita", "records": _records(), "recordCount": 30}


def paths(diffs):
    return [d["path"] for d in diffs]


# ---------------------------------------------------------------------------
# Unit: expansion
# ---------------------------------------------------------------------------


class TestExpandBulk:
    def test_where_field_range(self):
        diffs = expand_bulk(
            {
                "path": "/records/*/sectionId",
                "where": {
                    "slokNumber": {"gte": 1, "lte": 3},
                    "sectionId": "bhagavad_gita_ch_1",
                },
                "operation": "modify",
                "new_value": "abc",
            },
            DOC,
            100,
        )
        assert paths(diffs) == [f"/records/{i}/sectionId" for i in range(3)]
        assert all(d["old_value"] == "bhagavad_gita_ch_1" for d in diffs)
        assert all(d["new_value"] == "abc" for d in diffs)

    def test_index_for_positional_first_n(self):
        diffs = expand_bulk(
            {
                "path": "/records/*/status",
                "where": {"$index": {"lt": 20}},
                "new_value": "X",
            },
            DOC,
            100,
        )
        assert len(diffs) == 20
        assert diffs[-1]["path"] == "/records/19/status"

    def test_value_equality_is_case_insensitive(self):
        diffs = expand_bulk(
            {
                "path": "/records/*/sectionId",
                "where": {"$value": "BHAGAVAD_GITA_CH_2"},
                "operation": "modify",
                "new_value": "ch2",
            },
            DOC,
            100,
        )
        assert len(diffs) == 18

    def test_no_where_hits_every_element_and_skips_noops(self):
        doc = {"items": [{"v": 1}, {"v": 2}, {"v": 2}]}
        diffs = expand_bulk({"path": "/items/*/v", "new_value": 2}, doc, 100)
        assert paths(diffs) == ["/items/0/v"]  # the two already-2 are no-ops

    def test_delete_with_contains(self):
        doc = {
            "files": [
                {"title": "Regular Season 2026"},
                {"title": "Draft Season 2027 - Round 1"},
                {"title": "draft season 2027 - round 2"},
            ]
        }
        diffs = expand_bulk(
            {
                "path": "/files/*",
                "where": {"title": {"contains": "Draft Season 2027"}},
                "operation": "delete",
            },
            doc,
            100,
        )
        assert paths(diffs) == ["/files/1", "/files/2"]
        assert diffs[0]["old_value"] == doc["files"][1]

    def test_add_only_where_missing(self):
        doc = {"items": [{"a": 1}, {"a": 2, "flag": True}]}
        diffs = expand_bulk(
            {"path": "/items/*/flag", "operation": "add", "new_value": False}, doc, 100
        )
        assert paths(diffs) == ["/items/0/flag"]

    def test_object_wildcard_and_nested_where(self):
        doc = {
            "services": {
                "api": {"cfg": {"tier": "gold"}, "t": 1},
                "web": {"cfg": {"tier": "free"}, "t": 1},
            }
        }
        diffs = expand_bulk(
            {"path": "/services/*/t", "where": {"cfg/tier": "gold"}, "new_value": 9},
            doc,
            100,
        )
        assert paths(diffs) == ["/services/api/t"]

    def test_keys_with_slash_are_escaped(self):
        doc = {"m": {"a/b": {"x": 1}}}
        diffs = expand_bulk({"path": "/m/*/x", "new_value": 2}, doc, 100)
        assert paths(diffs) == ["/m/a~1b/x"]

    def test_type_mismatch_does_not_match(self):
        doc = {"items": [{"n": "abc"}, {"n": 5}]}
        diffs = expand_bulk(
            {"path": "/items/*/n", "where": {"$value": {"gt": 3}}, "new_value": 0},
            doc,
            100,
        )
        assert paths(diffs) == ["/items/1/n"]

    @pytest.mark.parametrize(
        "op, message",
        [
            ({"path": "/records/0/status", "new_value": 1}, "'*'"),
            ({"path": "/records/*/status", "operation": "rename"}, "unsupported"),
            (
                {"path": "/records/*/status", "where": {"status": {"like": "x"}}},
                "operator",
            ),
        ],
    )
    def test_malformed_ops_reported(self, op, message):
        diffs, notes = expand_all([op], DOC, 100)
        assert diffs == []
        assert message in notes[0]

    def test_match_cap(self):
        diffs, notes = expand_all(
            [{"path": "/records/*/status", "new_value": "Y"}], DOC, 10
        )
        assert diffs == []
        assert "more than 10" in notes[0]

    def test_overlapping_ops_deduplicated(self):
        ops = [
            {
                "path": "/records/*/status",
                "where": {"$index": {"lt": 5}},
                "new_value": "A",
            },
            {
                "path": "/records/*/status",
                "where": {"$index": {"lt": 8}},
                "new_value": "B",
            },
        ]
        diffs, _ = expand_all(ops, DOC, 100)
        assert len(diffs) == 8
        assert [d["new_value"] for d in diffs[:5]] == ["A"] * 5


class TestExtractBulk:
    def test_extracts_from_fenced_object(self):
        text = '```json\n{"diffs": [], "bulk": [{"path": "/a/*/b", "new_value": 1}], "explanation": "ok"}\n```'
        ops, explanation = extract_bulk(text)
        assert ops == [{"path": "/a/*/b", "new_value": 1}]
        assert explanation == "ok"

    def test_no_bulk(self):
        assert extract_bulk('{"diffs": [], "explanation": "x"}') == ([], "")
        assert extract_bulk("plain prose") == ([], "")


# ---------------------------------------------------------------------------
# Integration: chat pipeline with a skeleton-sized document
# ---------------------------------------------------------------------------


class FakeLLM:
    def __init__(self) -> None:
        self.replies: list[dict] = []
        self.calls: list[dict] = []

    async def invoke(self, session_id, message, principal, system_prompt, **kw):
        self.calls.append({"system": system_prompt, "history": kw.get("history") or []})
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(self.replies.pop(0))}
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

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    # Force the skeleton path for this small document (as for gita.json).
    monkeypatch.setenv("LLM_MAX_INLINE_CHARS", "500")
    get_settings.cache_clear()
    with TestClient(app, headers={"X-API-Key": f"bulk-{uuid.uuid4().hex}"}) as c:
        yield c


@pytest.fixture
def sid(client):
    sid = client.post("/api/sessions", json={"name": "bulk"}).json()["id"]
    client.post(
        "/api/json/upload",
        files={"json_body": (None, json.dumps(DOC)), "session_id": (None, sid)},
    )
    return sid


def chat(client, sid, message):
    resp = client.post("/api/chat", data={"session_id": sid, "message": message})
    return [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]


class TestBulkChat:
    def test_skeleton_prompt_offers_bulk_not_refusal(self, client, sid, llm):
        llm.replies = [{"diffs": [], "explanation": "x"}]
        chat(client, sid, "hi")
        system = llm.calls[0]["system"]
        assert "STRUCTURAL SKELETON" in system
        assert "BULK EDITS" in system
        assert 'use a "bulk" op' in system

    def test_first_20_records_via_bulk(self, client, sid, llm):
        llm.replies = [
            {
                "diffs": [],
                "bulk": [
                    {
                        "path": "/records/*/sectionId",
                        "where": {"$index": {"lt": 20}},
                        "operation": "modify",
                        "new_value": "abc",
                    }
                ],
                "explanation": "Set sectionId to abc for the first 20 records.",
            }
        ]
        events = chat(client, sid, "first 20 ?")

        diff_events = [p["entry"] for e, p in events if e == "diff"]
        assert len(diff_events) == 20
        assert (
            diff_events[13]["old_value"] == "bhagavad_gita_ch_2"
        )  # real value, not guessed
        done = next(p for e, p in events if e == "complete")
        assert "matched 20 location(s)" in done["explanation"]
        records = done["working_json"]["records"]
        assert [r["sectionId"] for r in records].count("abc") == 20
        assert records[20]["sectionId"] == "bhagavad_gita_ch_2"

        # Accept-all promotes all 20; history keeps the op for follow-ups.
        body = client.post(f"/api/sessions/{sid}/diffs/accept-all").json()
        assistant = body["conversation_history"][1]
        assert assistant["bulk"][0]["where"] == {"$index": {"lt": 20}}
        assert {d["status"] for d in assistant["diffs"]} == {"accepted"}

    def test_follow_up_replays_bulk_op(self, client, sid, llm):
        op = {
            "path": "/records/*/status",
            "where": {"sectionId": "bhagavad_gita_ch_1"},
            "new_value": "DONE",
        }
        llm.replies = [
            {"diffs": [], "bulk": [op], "explanation": "Marked chapter 1 done."},
            {"diffs": [], "explanation": "ok"},
        ]
        chat(client, sid, "mark chapter 1 done")
        chat(client, sid, "now the same for chapter 2")

        replay = json.loads(llm.calls[1]["history"][1]["content"])
        assert replay["bulk"] == [op]
        assert len(replay["diffs"]) == 12

    def test_bulk_matching_nothing_reports_it(self, client, sid, llm):
        llm.replies = [
            {
                "diffs": [],
                "bulk": [
                    {
                        "path": "/records/*/status",
                        "where": {"sectionId": "nope"},
                        "new_value": "X",
                    }
                ],
                "explanation": "Updated all matching records.",
            }
        ]
        events = chat(client, sid, "update nope")
        done = next(p for e, p in events if e == "complete")
        assert "matched nothing" in done["explanation"]
        assert done["working_json"] == DOC


# ---------------------------------------------------------------------------
# Skeleton field stats + local Ollama params
# ---------------------------------------------------------------------------


def test_array_stats_flag_non_unique_counter():
    from src.json_ai_studio.prompting import build_array_stats

    (line,) = build_array_stats(DOC)
    assert line.startswith("/records/* (30 items):")
    assert "slokNumber: 18 distinct, range 1..18" in line
    assert '"bhagavad_gita_ch_2"×18' in line


def test_ollama_disables_thinking_and_sets_context(monkeypatch):
    from src.json_ai_studio.providers.ollama import OllamaProvider

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    get_settings.cache_clear()
    p = OllamaProvider(
        {
            "enabled": True,
            "base_model": "gemma4:12b",
            "reasoning": "none",
            "models": ["gemma4:12b"],
        },
        get_settings(),
    )
    assert p.completion_params("gemma4:12b") == {"think": False, "num_ctx": 32768}
    p.supports_thinking = True
    assert p.completion_params("gemma4:12b", "high")["think"] is True


class TestCopyFromField:
    """Prod 2026-10-14: 'i want all of the modifiedDate to match the
    creationDate' on a 600-entry doc wrote the placeholder
    'REPLACE_WITH_CORRESPONDING_CREATION_DATE' into every entry."""

    DOC = {
        "entries": [
            {"creationDate": "2025-01-10", "modifiedDate": "2026-01-20"},
            {"creationDate": "2025-02-11", "modifiedDate": "2025-02-11"},
            {"modifiedDate": "2026-03-22"},  # no source field
            {"creationDate": {"d": "2025-04-13"}, "modifiedDate": "x"},
        ]
    }

    def test_copies_each_elements_own_value(self):
        diffs = expand_bulk(
            {
                "path": "/entries/*/modifiedDate",
                "operation": "modify",
                "new_value": {"$from": "creationDate"},
            },
            self.DOC,
            100,
        )
        # [1] already equal (no-op), [2] has no creationDate (skipped)
        assert [(d["path"], d["new_value"]) for d in diffs] == [
            ("/entries/0/modifiedDate", "2025-01-10"),
            ("/entries/3/modifiedDate", {"d": "2025-04-13"}),
        ]
        assert diffs[0]["old_value"] == "2026-01-20"

    def test_copied_objects_are_independent(self):
        _, diff = expand_bulk(
            {"path": "/entries/*/modifiedDate", "new_value": {"$from": "creationDate"}},
            self.DOC,
            100,
        )
        diff["new_value"]["d"] = "mutated"
        assert self.DOC["entries"][3]["creationDate"] == {"d": "2025-04-13"}

    def test_prompt_documents_from(self):
        from src.json_ai_studio.prompting import build_system_prompt

        assert '{"$from":' in build_system_prompt({"a": 1})


class TestBulkRobustness:
    """Live replays 2026-10-21 (gemma4:12b): `neq` was rejected as unknown, and
    a pattern one level too shallow wrote 60 over a whole parameters array."""

    DOC = {"players": [{"p": [99, 70, 99]}, {"p": [55, 99, 1]}]}

    @pytest.mark.parametrize("op", ["neq", "!=", "not_equal"])
    def test_operator_aliases(self, op):
        diffs = expand_bulk(
            {"path": "/players/*/p/*", "where": {"$value": {op: 99}}, "new_value": 0},
            self.DOC,
            100,
        )
        assert [d["path"] for d in diffs] == [
            "/players/0/p/1",
            "/players/1/p/0",
            "/players/1/p/2",
        ]

    def test_refuses_replacing_container_with_scalar(self):
        diffs, notes = expand_all(
            [{"path": "/players/*/p", "new_value": 60}], self.DOC, 100
        )
        assert diffs == []
        assert "target the elements" in notes[0]

    def test_element_level_pattern_works(self):
        diffs = expand_bulk(
            {"path": "/players/*/p/*", "where": {"$value": 99}, "new_value": 60},
            self.DOC,
            100,
        )
        assert [d["path"] for d in diffs] == [
            "/players/0/p/0",
            "/players/0/p/2",
            "/players/1/p/1",
        ]

    def test_from_may_copy_containers(self):
        doc = {"items": [{"a": [1], "b": [2]}]}
        diffs = expand_bulk(
            {"path": "/items/*/b", "new_value": {"$from": "a"}}, doc, 100
        )
        assert diffs[0]["new_value"] == [1]
