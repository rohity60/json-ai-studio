"""Batch read sized by the deployment's limits, outline, where clean-up
(PRD C §5: C-40..C-44)."""

import json
from types import SimpleNamespace

from src.json_ai_studio.bulk_edits import expand_bulk, normalize_where
from src.json_ai_studio.json_tools import JsonToolbox
from src.json_ai_studio.providers.policy import DeploymentPolicy
from src.json_ai_studio.services import deployment_budget as budget
from src.json_ai_studio.services import progress
from src.json_ai_studio.services.turn_planner import tool_result_room_chars


def _doc(n=40, chars=300):
    return {
        "entries": [
            {"id": f"rule-{i:03d}", "content": f"entry {i} " + "x" * chars}
            for i in range(n)
        ]
    }


def _call(box, name, **args):
    return json.loads(box.call(name, json.dumps(args)))


def test_range_returns_as_many_records_as_the_room_allows():
    box = JsonToolbox(_doc(), 4000, 60_000)
    box.set_batch_room(2_000)  # below one single result → floor of 4,000
    small = _call(box, "read", path="/entries/0..39")
    box.set_batch_room(12_000)
    big = _call(box, "read", path="/entries/0..39")
    assert 5 <= small["returned"] < big["returned"] < 40
    assert big["requested"] == 40
    assert big["remaining"] == 40 - big["returned"]
    assert big["next_paths"][0] == f"/entries/{big['returned']}"
    assert [r["path"] for r in big["results"][:2]] == ["/entries/0", "/entries/1"]
    assert big["results"][0]["value"]["id"] == "rule-000"


def test_batch_result_never_exceeds_the_room_and_is_valid_json():
    box = JsonToolbox(_doc(), 4000, 60_000)
    box.set_batch_room(9_000)
    text = box.call("read", {"paths": ["/entries/0..39"]})
    assert len(text) <= 9_000
    assert json.loads(text)["returned"] > 0


def test_room_is_capped_and_shared_within_a_round():
    box = JsonToolbox(_doc(400), 4000, 10_000)
    box.set_batch_room(1_000_000)
    assert box.batch_room == 10_000  # hard cap
    first = _call(box, "read", path="/entries/0..")
    second = _call(box, "read", path="/entries/100..")
    assert second["returned"] < first["returned"]  # room already spent
    box.set_batch_room(None)  # no known limit → three single results
    assert box.batch_room == 10_000


def test_paths_list_missing_path_and_everything_fits():
    box = JsonToolbox(_doc(3), 4000)
    out = _call(box, "read", paths=["/entries/2/id", "/entries/9", "/entries/0/id"])
    assert out["returned"] == 3 and "next_paths" not in out
    assert out["results"][0]["value"] == "rule-002"
    assert "no such index" in out["results"][1]["error"]


def test_oversized_first_record_is_paged_like_a_single_read():
    box = JsonToolbox({"entries": ["word " * 5000, "b"]}, 4000)
    out = _call(box, "read", path="/entries/0..1")
    # the long string comes back as its first page; the next value still fits
    assert out["returned"] == 2
    assert out["results"][0]["next_offset"] > 0
    assert out["results"][1]["value"] == "b"


def test_range_errors():
    box = JsonToolbox(_doc(3), 4000)
    assert "only 3 items" in _call(box, "read", path="/entries/5..9")["error"]
    assert "need an array" in _call(box, "read", path="/entries/0/0..2")["error"]
    # a plain single read is unchanged
    assert _call(box, "read", path="/entries/1/id")["value"] == "rule-001"


def test_room_follows_token_budget_and_context_window():
    budget.reset()
    msgs = [{"role": "user", "content": "x" * 12_000}]
    pol = DeploymentPolicy.from_config({"budget_headroom": 0.8})
    tight = SimpleNamespace(
        name="g", tpm_input_limit=16_000, context_tokens=128_000, policy=pol
    )
    roomy = SimpleNamespace(
        name="n", tpm_input_limit=None, context_tokens=128_000, policy=pol
    )
    unlimited = SimpleNamespace(name="o", tpm_input_limit=None, context_tokens=None)
    a = tool_result_room_chars(tight, "m", msgs)
    b = tool_result_room_chars(roomy, "m", msgs)
    assert 0 < a < b
    # fuller conversation → less room
    more = msgs + [{"role": "tool", "content": "y" * 12_000}]
    assert tool_result_room_chars(tight, "m", more) < a
    assert tool_result_room_chars(unlimited, "unknown-model-xyz", msgs) is None


def test_outline_lists_largest_strings_and_arrays_without_values():
    doc = {
        "data": {"description": "d" * 5000, "name": "n"},
        "entries": _doc(5)["entries"],
    }
    box = JsonToolbox(doc, 4000)
    out = _call(box, "outline")
    assert out["top"][0] == {"path": "/data/description", "type": "str", "chars": 5000}
    arr = next(r for r in out["top"] if r["path"] == "/entries")
    assert arr["items"] == 5 and arr["avg_item_chars"] > 300
    assert "ddddd" not in json.dumps(out)
    assert _call(box, "outline", path="/entries", top=1)["truncated"] is True


def test_where_keys_with_quotes_match_like_plain_keys():
    assert normalize_where({'"id"': {'"GTE"': 5}, '\\"n\\"': 1}) == {
        "id": {"gte": 5},
        "n": 1,
    }
    box = JsonToolbox({"rows": [{"n": 1}, {"n": 7}]}, 4000)
    quoted = _call(box, "query", path="/rows/*", where={'"n"': {'"gte"': 5}})
    plain = _call(box, "query", path="/rows/*", where={"n": {"gte": 5}})
    assert quoted["total"] == plain["total"] == 1
    diffs = expand_bulk(
        {"path": "/rows/*/n", "where": {'"n"': {'"gte"': 5}}, "new_value": 0},
        {"rows": [{"n": 1}, {"n": 7}]},
        10,
    )
    assert [d["path"] for d in diffs] == ["/rows/1/n"]


def test_number_comparison_on_text_field_gets_a_hint():
    box = JsonToolbox(_doc(3), 4000)
    out = _call(box, "query", path="/entries/*", where={"id": {"gte": 5}})
    assert out["total"] == 0 and "$index" in out["hint"]
    ok = _call(box, "query", path="/entries/*", where={"$index": {"gte": 1}})
    assert ok["total"] == 2 and "hint" not in ok


def test_progress_lines_for_batch_read_and_outline():
    box = JsonToolbox(_doc(), 4000, 60_000)
    box.call("read", {"path": "/entries/0..39"})
    line = progress.describe_tool_call(
        "read", {"path": "/entries/0..39"}, box.last_result
    )
    assert line.startswith("Read ") and "/entries/0 … /entries/" in line
    assert "more did not fit this AI model's limit" in line
    assert "xxxx" not in line
    box.call("outline", {})
    assert progress.describe_tool_call("outline", {}, box.last_result).startswith(
        "Measured the document ("
    )


def test_last_round_says_stop_and_report_instead_of_read_more():
    box = JsonToolbox(_doc(), 4000, 60_000)
    box.set_batch_room(12_000, last_round=True)
    out = _call(box, "read", path="/entries/0..39")
    assert "next_paths" not in out
    assert out["covered"]["first"] == "/entries/0"
    assert out["continue_from"] == f"/entries/{out['returned']}"
    assert "Do NOT read again" in out["hint"]
    # room down to one single result → same, even before the last round
    box.set_batch_room(5_000)
    assert "continue_from" in _call(box, "read", path="/entries/0..39")
    # plenty of room, not the last round → keep reading
    box.set_batch_room(12_000)
    assert "next_paths" in _call(box, "read", path="/entries/0..39")


def test_explicit_range_reads_only_that_range():
    box = JsonToolbox(_doc(60, 50), 4000, 60_000)
    box.set_batch_room(12_000)
    out = _call(box, "read", path="/entries/40..50")
    assert [r["path"] for r in out["results"]] == [
        f"/entries/{i}" for i in range(40, 51)
    ]
    assert "remaining" not in out
