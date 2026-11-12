"""In-string text edits (replace_text) + paged string reads.

A long string the model saw only truncated must be fixable without rewriting
it whole (prod 2026-11-12: card description 7,485 chars, the model's rewrite
was 232 chars and the edit-safety guard refused it). replace_text names only
the snippet; the server expands it into one full-value modify diff.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from src.json_ai_studio.diff_utils import normalize_entry, parse_llm_response
from src.json_ai_studio.gateway import GatewayService
from src.json_ai_studio.json_tools import JsonToolbox
from src.json_ai_studio.prompting import build_system_prompt
from src.json_ai_studio.services.chat_service import parse_sse
from src.json_ai_studio.services.progress import describe_tool_call
from src.json_ai_studio.text_edits import expand_text_edits

LONG = (
    "Femtora is a Fantasy world with Elves, Dwarves, Halfings, Beast-foke. "
    + "The world is matriarchal and old. " * 250
    + "Halfings are small."
)
DOC = {"data": {"name": "Narrator", "description": LONG, "tags": ["a"], "n": 3}}


def te(path, find, replace, **kw):
    return {
        "path": path,
        "operation": "replace_text",
        "find": find,
        "replace": replace,
        **kw,
    }


class TestNormalize:
    def test_replace_text_kept_with_find_replace(self):
        e = normalize_entry(te("data/description", "Halfings", "Halflings"))
        assert e == {
            "path": "/data/description",
            "operation": "replace_text",
            "find": "Halfings",
            "replace": "Halflings",
            "all": False,
        }

    def test_synonyms_and_alt_keys(self):
        e = normalize_entry(
            {
                "path": "/a",
                "op": "find_replace",
                "old_text": "x",
                "new_text": "y",
                "all": True,
            }
        )
        assert (e["operation"], e["find"], e["replace"], e["all"]) == (
            "replace_text",
            "x",
            "y",
            True,
        )

    def test_missing_find_is_dropped(self):
        assert (
            normalize_entry({"path": "/a", "operation": "replace_text", "replace": "y"})
            is None
        )

    def test_missing_replace_deletes(self):
        assert (
            normalize_entry({"path": "/a", "operation": "replace_text", "find": "x"})[
                "replace"
            ]
            == ""
        )

    def test_parsed_from_llm_response(self):
        text = json.dumps(
            {
                "diffs": [te("/data/description", "Beast-foke", "Beast-folk")],
                "explanation": "e",
            }
        )
        diffs, explanation = parse_llm_response(text)
        assert diffs[0]["operation"] == "replace_text" and explanation == "e"


class TestExpand:
    def test_edits_on_one_path_merge_into_one_modify(self):
        out, notes = expand_text_edits(
            [
                te("/data/description", "Beast-foke", "Beast-folk"),
                te("/data/description", "Halfings", "Halflings", all=True),
            ],
            DOC,
        )
        assert notes == []
        assert len(out) == 1
        d = out[0]
        assert d["operation"] == "modify" and d["path"] == "/data/description"
        assert d["old_value"] == LONG
        assert d["new_value"] == LONG.replace("Beast-foke", "Beast-folk").replace(
            "Halfings", "Halflings"
        )
        assert len(d["new_value"]) == len(LONG) + 2  # nothing else dropped

    def test_ambiguous_find_is_refused_without_all(self):
        out, notes = expand_text_edits(
            [te("/data/description", "Halfings", "Halflings")], DOC
        )
        assert out == []
        assert "occurs 2 times" in notes[0]

    def test_unique_context_snippet_applies(self):
        out, _ = expand_text_edits(
            [te("/data/description", "Halfings are", "Halflings are")], DOC
        )
        assert out[0]["new_value"].endswith("Halflings are small.")
        assert out[0]["new_value"].count("Halfings") == 1

    def test_completing_a_cut_off_word_is_refused(self):
        doc = {"s": "MP should Regenerate over time scaled with Intelligence\nSP"}
        out, notes = expand_text_edits(
            [te("/s", "scaled with In", "scaled with Intelligence")], doc
        )
        assert out == [] and "part of a word" in notes[0]

    def test_match_starting_inside_a_word_is_refused(self):
        doc = {"s": "track the {{user}}'s stats"}
        out, notes = expand_text_edits(
            [te("/s", "he {{user}}'s stats", "the {{user}}'s stats")], doc
        )
        assert out == [] and "part of a word" in notes[0]

    def test_all_checks_every_occurrence(self):
        doc = {"s": "an Elf, two Elfs"}
        out, notes = expand_text_edits([te("/s", "Elf", "Elve", all=True)], doc)
        assert out == [] and "part of a word" in notes[0]

    def test_real_suffix_fix_still_applies(self):
        doc = {"s": "a three tailed fox"}
        out, _ = expand_text_edits([te("/s", "three tailed", "three-tailed")], doc)
        assert out[0]["new_value"] == "a three-tailed fox"
        doc = {"s": "the Halfing lives"}  # find ends at word boundary
        out, _ = expand_text_edits([te("/s", "Halfing", "Halfling")], doc)
        assert out[0]["new_value"] == "the Halfling lives"

    def test_not_found(self):
        out, notes = expand_text_edits(
            [te("/data/description", "Goblinz", "Goblins")], DOC
        )
        assert out == [] and "was not found" in notes[0]

    def test_non_string_target(self):
        out, notes = expand_text_edits([te("/data/n", "3", "4")], DOC)
        assert out == [] and "not a text value" in notes[0]
        out, notes = expand_text_edits([te("/data/missing", "x", "y")], DOC)
        assert out == [] and "not a text value" in notes[0]

    def test_partial_failure_still_applies_the_rest(self):
        out, notes = expand_text_edits(
            [
                te("/data/description", "Goblinz", "Goblins"),
                te("/data/description", "Beast-foke", "Beast-folk"),
            ],
            DOC,
        )
        assert len(out) == 1 and "Beast-folk" in out[0]["new_value"]
        assert len(notes) == 1

    def test_plain_diff_on_same_path_wins(self):
        plain = {
            "path": "/data/description",
            "operation": "modify",
            "old_value": LONG,
            "new_value": "x",
        }
        out, notes = expand_text_edits(
            [plain, te("/data/description", "Beast-foke", "Beast-folk")], DOC
        )
        assert out == [plain] and "already changed" in notes[0]

    def test_other_diffs_pass_through_in_order(self):
        other = {
            "path": "/data/name",
            "operation": "modify",
            "old_value": "Narrator",
            "new_value": "N",
        }
        out, _ = expand_text_edits(
            [other, te("/data/description", "Beast-foke", "Beast-folk")], DOC
        )
        assert out[0] is other and out[1]["path"] == "/data/description"

    def test_no_edits_is_identity(self):
        diffs = [{"path": "/a", "operation": "modify"}]
        assert expand_text_edits(diffs, DOC) == (diffs, [])


class TestPagedRead:
    def test_long_string_pages_cover_whole_text_exactly(self):
        box = JsonToolbox(DOC)
        pieces, offset, pages = [], 0, 0
        while True:
            raw = box.call("read", {"path": "/data/description", "offset": offset})
            assert len(raw) <= box.result_max_chars  # never hits the hard cap
            r = json.loads(raw)
            assert r["length"] == len(LONG) and r["offset"] == offset
            pieces.append(r["text"])
            pages += 1
            if "next_offset" not in r:
                break
            assert "offset=" in r["hint"] and "replace_text" in r["hint"]
            offset = r["next_offset"]
        assert "".join(pieces) == LONG
        assert pages >= 3
        for p in pieces[:-1]:  # pages never end mid-word
            assert p[-1].isspace()

    def test_escape_heavy_text_still_fits(self):
        doc = {"s": 'line "q"\n' * 2000}
        raw = JsonToolbox(doc).call("read", {"path": "/s"})
        assert len(raw) <= 4000
        r = json.loads(raw)
        assert doc["s"].startswith(r["text"]) and r["next_offset"] == len(r["text"])

    def test_short_values_unchanged(self):
        r = json.loads(JsonToolbox(DOC).call("read", {"path": "/data/name"}))
        assert r == {"path": "/data/name", "type": "str", "value": "Narrator"}

    def test_offset_on_short_string_pages(self):
        r = json.loads(
            JsonToolbox(DOC).call("read", {"path": "/data/name", "offset": 4})
        )
        assert r["text"] == "ator" and "next_offset" not in r

    def test_schema_and_instructions_mention_paging(self):
        read = next(s for s in JsonToolbox.schemas() if s["function"]["name"] == "read")
        assert "offset" in read["function"]["parameters"]["properties"]
        valid = {"string", "integer", "number", "boolean", "object", "array"}
        for s in JsonToolbox.schemas():
            for prop in s["function"]["parameters"]["properties"].values():
                assert prop.get("type", "string") in valid
        assert "next_offset" in JsonToolbox.INSTRUCTIONS
        assert "replace_text" in JsonToolbox.INSTRUCTIONS

    def test_progress_line_shows_range(self):
        result = json.loads(
            JsonToolbox(DOC).call("read", {"path": "/data/description"})
        )
        line = describe_tool_call("read", {"path": "/data/description"}, result, DOC)
        assert line.startswith("Read /data/description (characters 1–")
        assert f"of {len(LONG):,})" in line


def test_prompt_documents_text_edits():
    prompt = build_system_prompt({"a": 1})
    assert "TEXT EDITS" in prompt
    assert '"operation": "replace_text"' in prompt
    assert 'Never "modify" a string you only saw truncated' in prompt


# -- end to end through /api/chat (stubbed LLM) ------------------------------


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.json_ai_studio.main import app

    monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "10000")
    with TestClient(app, headers={"X-API-Key": f"te-{uuid.uuid4().hex}"}) as c:
        yield c


@pytest.fixture
def replies(monkeypatch):
    queue: list[dict] = []

    async def fake_invoke(session_id, message, principal, system_prompt, **kw):
        if kw.get("planner"):
            kw["planner"](SimpleNamespace(name="fake"), "fake/m")
        yield "event: thinking\ndata: " + json.dumps(
            {"text": json.dumps(queue.pop(0))}
        ) + "\n\n"

    monkeypatch.setattr(GatewayService, "invoke", staticmethod(fake_invoke))
    return queue


def _chat(client, sid, message):
    resp = client.post("/api/chat", data={"session_id": sid, "message": message})
    return [parse_sse(b) for b in resp.text.split("\n\n") if b.strip()]


def _seed(client):
    sid = client.post("/api/sessions", json={"name": "te"}).json()["id"]
    r = client.post(
        f"/api/sessions/{sid}/versions/restore",
        json={"versions": [], "working_json": DOC, "conversation_history": []},
    )
    assert r.status_code == 200, r.text
    return sid


def test_chat_applies_text_edits_to_full_long_string(client, replies):
    sid = _seed(client)
    replies.append(
        {
            "diffs": [
                te("/data/description", "Halfings", "Halflings", all=True),
                te("/data/description", "Beast-foke", "Beast-folk"),
            ],
            "explanation": "Fixed 2 typos.",
        }
    )
    events = _chat(client, sid, "Fix the spelling mistakes in the description")
    diffs = [p["entry"] for e, p in events if e == "diff"]
    assert len(diffs) == 1
    assert diffs[0]["operation"] == "modify"
    assert diffs[0]["old_value"] == LONG
    fixed = LONG.replace("Halfings", "Halflings").replace("Beast-foke", "Beast-folk")
    assert diffs[0]["new_value"] == fixed
    done = next(p for e, p in events if e == "complete")
    assert done["working_json"]["data"]["description"] == fixed
    assert done["explanation"] == "Fixed 2 typos."


def test_chat_reports_failed_text_edit(client, replies):
    sid = _seed(client)
    replies.append(
        {
            "diffs": [te("/data/description", "Goblinz", "Goblins")],
            "explanation": "Fixed Goblinz.",
        }
    )
    events = _chat(client, sid, "fix goblinz")
    assert not [p for e, p in events if e == "diff"]
    done = next(p for e, p in events if e == "complete")
    assert "'Goblinz' was not found" in done["explanation"]
    assert done["working_json"]["data"]["description"] == LONG
