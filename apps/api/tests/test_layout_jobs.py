"""Layout instructions in review jobs (layout.py), replaying the live
2026-11-23 nvidia failures: pack copied into records, records wrapped,
records inserted, own names dropped, layouts differing between batches."""

from __future__ import annotations

import json

import pytest

from src.json_ai_studio import layout as L
from src.json_ai_studio.settings import get_settings
from tests.test_jobs_api import (  # noqa: F401  (fixtures)
    clean_budget,
    client,
    create_job,
    event,
    llm,
    new_session,
    next_batch,
    session_of,
)

EXAMPLE = {
    "pack": {"id": "MyPack"},
    "skins": [
        {
            "id": "Steve",
            "geometry": "models/steve.obj",
            "textures": {"body": "steve.png"},
        }
    ],
}
INSTRUCTION = "Review all skins and make each one match this layout: " + json.dumps(
    EXAMPLE
)
N = 12


def doc():
    return {
        "skins": [
            {
                "localization_name": f"Skin {i}",
                "geometry": f"geometry.s{i}",
                "texture": f"s{i}.png",
                "type": "free",
            }
            for i in range(N)
        ]
    }


def good(records):
    diffs = []
    for r in records:
        p = r["path"]
        diffs += [
            {"path": p + "/id", "operation": "move", "from": p + "/localization_name"},
            {"path": p + "/textures/body", "operation": "move", "from": p + "/texture"},
            {"path": p + "/type", "operation": "delete"},
        ]
    return {"diffs": diffs, "explanation": "ok"}


def with_extra(records, extra):
    out = good(records)
    out["diffs"] += extra(records)
    return out


@pytest.fixture
def small_batches(monkeypatch):
    monkeypatch.setattr(get_settings(), "job_max_records_per_batch", 4)


@pytest.fixture
def job(client, llm, small_batches):
    sid = new_session(client, doc())
    j = create_job(client, sid, scope_path="/skins", instruction=INSTRUCTION)
    assert j.status_code == 201, j.text
    return sid, j.json()["id"]


# -- unit ----------------------------------------------------------------------


def test_layout_for_splits_record_and_top_level():
    lay = L.layout_for(INSTRUCTION, doc(), "/skins")
    assert lay.keys == ["id", "geometry", "textures"]
    assert lay.top_level == {"pack": {"id": "MyPack"}}
    assert L.layout_for("fix the typos", doc(), "/skins") is None
    # Already has pack → nothing to add at the top.
    assert L.layout_for(INSTRUCTION, {**doc(), "pack": 1}, "/skins").top_level == {}


def test_prompt_rules_name_keys_and_top_level():
    text = L.prompt_rules(L.layout_for(INSTRUCTION, doc(), "/skins"))
    assert '["id", "geometry", "textures"]' in text and '"pack"' in text


# -- job API -------------------------------------------------------------------


def test_good_batches_apply_and_pack_added_once(client, llm, job):
    sid, jid = job
    llm.reply = good
    first = event(next_batch(client, sid, jid), "batch_complete")
    assert any(d["path"] == "/pack" for d in first["diffs"])
    assert "LAYOUT CHANGE" in llm.plans[0].messages[0]["content"]
    second = event(next_batch(client, sid, jid), "batch_complete")
    assert not any(d["path"] == "/pack" for d in second["diffs"])
    w = session_of(client, sid)["working_json"]
    assert w["pack"] == {"id": "MyPack"}
    assert w["skins"][0] == {
        "geometry": "geometry.s0",
        "id": "Skin 0",
        "textures": {"body": "s0.png"},
    }


@pytest.mark.parametrize(
    "extra, says",
    [
        (  # pack copied into every record
            lambda rs: [
                {"path": r["path"] + "/pack", "operation": "add", "new_value": {}}
                for r in rs
            ],
            'key "pack"',
        ),
        (  # a record wrapped as {pack, skins}
            lambda rs: [
                {
                    "path": rs[0]["path"],
                    "operation": "modify",
                    "new_value": {"pack": {}, "skins": [rs[0]["value"]]},
                }
            ],
            "key",
        ),
        (  # a record inserted
            lambda rs: [
                {"path": "/skins/1", "operation": "add", "new_value": {"id": "x"}}
            ],
            "added or removed",
        ),
    ],
)
def test_broken_layout_fails_batch_and_retry_is_told(client, llm, job, extra, says):
    sid, jid = job
    before = session_of(client, sid)["working_json"]
    llm.reply = lambda rs: with_extra(rs, extra)
    failed = event(next_batch(client, sid, jid), "batch_failed")
    assert failed and says in failed["error"]
    assert failed["job"]["cursor"] == 0
    assert session_of(client, sid)["working_json"] == before  # nothing applied

    llm.reply = good
    done = event(next_batch(client, sid, jid), "batch_complete")
    assert "broke the target layout" in llm.plans[1].messages[0]["content"]
    assert llm.batches[1] == llm.batches[0]  # the same records again
    assert done["cursor"] == len(llm.batches[1])
    nxt = event(next_batch(client, sid, jid), "batch_complete")
    assert nxt and "broke the target layout" not in llm.plans[2].messages[0]["content"]


def test_dropped_own_names_fail(client, llm, job):
    sid, jid = job

    def lose_names(records):
        out = good(records)
        out["diffs"] = [
            (
                {**d, "operation": "delete", "path": d["from"]}
                if d.get("from", "").endswith("localization_name")
                else d
            )
            for d in out["diffs"]
        ]
        for d in out["diffs"]:
            d.pop("from", None) if d["operation"] == "delete" else None
        return out

    llm.reply = lose_names
    failed = event(next_batch(client, sid, jid), "batch_failed")
    assert failed and "localization_name" in failed["error"]


def test_later_batch_with_other_shape_fails(client, llm, job):
    sid, jid = job
    llm.reply = good
    event(next_batch(client, sid, jid), "batch_complete")

    def keep_type(records):
        out = good(records)
        out["diffs"] = [d for d in out["diffs"] if d["operation"] != "delete"]
        return out

    llm.reply = keep_type
    failed = event(next_batch(client, sid, jid), "batch_failed")
    assert failed and 'still have "type"' in failed["error"]


def test_no_example_means_no_layout_rules(client, llm, small_batches):
    sid = new_session(client, doc())
    jid = create_job(
        client, sid, scope_path="/skins", instruction="Review all skins for typos"
    ).json()["id"]
    llm.reply = lambda rs: {"diffs": [], "explanation": "fine"}
    event(next_batch(client, sid, jid), "batch_complete")
    assert "LAYOUT CHANGE" not in llm.plans[0].messages[0]["content"]


def test_layout_batches_sized_for_larger_answers(client, llm):
    # No record cap: the answer-size limit alone decides.
    many = {"skins": doc()["skins"] * 40}  # 480 records
    sid = new_session(client, many)
    plain = create_job(client, sid, scope_path="/skins", instruction="Review all skins")
    llm.reply = lambda rs: {"diffs": [], "explanation": "fine"}
    event(next_batch(client, sid, plain.json()["id"]), "batch_complete")
    client.delete(f"/api/sessions/{sid}/jobs/{plain.json()['id']}")
    lay = create_job(client, sid, scope_path="/skins", instruction=INSTRUCTION)
    event(next_batch(client, sid, lay.json()["id"]), "batch_complete")
    assert len(llm.batches[1]) < len(llm.batches[0]) / 2


def test_cut_off_answer_caps_next_batch_by_records_answered(client, llm):
    many = {"skins": doc()["skins"] * 40}
    sid = new_session(client, many)
    jid = create_job(client, sid, scope_path="/skins", instruction=INSTRUCTION).json()[
        "id"
    ]
    cut = json.dumps(good(llm_records(0, 30)))[:-200]  # 30 records, cut in the 30th
    llm.script = [cut]
    failed = event(next_batch(client, sid, jid), "batch_failed")
    assert "cut off" in failed["error"]
    llm.reply = good
    event(next_batch(client, sid, jid), "batch_complete")
    assert len(llm.batches[1]) <= int(29 * 0.8)
    event(next_batch(client, sid, jid), "batch_complete")
    assert len(llm.batches[2]) <= int(29 * 0.8)  # sticky


def llm_records(start, n):
    return [{"path": f"/skins/{i}", "value": {}} for i in range(start, start + n)]


def test_first_batch_missing_example_key_fails(client, llm, job):
    # Live 2026-11-23: batch 1 dropped "model" and was accepted; its shape
    # then made a later, correct batch fail. Target = the example's keys.
    sid, jid = job

    def no_textures(records):
        out = good(records)
        out["diffs"] = [d for d in out["diffs"] if "textures" not in d["path"]]
        return out

    llm.reply = no_textures
    failed = event(next_batch(client, sid, jid), "batch_failed")
    assert 'lack the example\'s key "textures"' in failed["error"]
    assert 'still have "texture"' in failed["error"]
    llm.reply = good
    assert event(next_batch(client, sid, jid), "batch_complete")


def test_whole_record_modify_answer_applies_and_rejects_cleanly(client, llm, job):
    # The prompt's answer form: one compact modify per record, no old_value.
    sid, jid = job

    def whole(records):
        return {
            "diffs": [
                {
                    "path": r["path"],
                    "operation": "modify",
                    "new_value": {
                        "id": r["value"]["localization_name"],
                        "geometry": r["value"]["geometry"],
                        "textures": {"body": r["value"]["texture"]},
                    },
                }
                for r in records
            ],
            "explanation": "ok",
        }

    llm.reply = whole
    done = event(next_batch(client, sid, jid), "batch_complete")
    rec = next(d for d in done["diffs"] if d["path"] == "/skins/0")
    assert rec["old_value"]["localization_name"] == "Skin 0"
    r = client.post(f"/api/sessions/{sid}/diffs/{rec['id']}/reject")
    assert r.status_code == 200, r.text
    assert session_of(client, sid)["working_json"]["skins"][0] == doc()["skins"][0]


# -- layout_for input shapes ---------------------------------------------------

REC = {"id": "Steve", "geometry": "g.obj"}


@pytest.mark.parametrize(
    "message",
    [
        "Make each skin look like this: " + json.dumps([REC]),  # bare list
        "Make each skin look like this: " + json.dumps(REC),  # one record
        "Use {id} names. Layout: " + json.dumps({"skins": [REC]}),  # prose braces
    ],
    ids=["list", "record", "prose_braces"],
)
def test_layout_for_example_shapes(message):
    lay = L.layout_for(message, doc(), "/skins")
    assert lay is not None and lay.element == REC and lay.top_level == {}


def test_layout_for_nested_scope_adds_no_top_level_keys():
    nested = {"packs": [doc()]}
    msg = "Match: " + json.dumps(EXAMPLE)
    lay = L.layout_for(msg, nested, "/packs/0/skins")
    assert lay.keys == ["id", "geometry", "textures"]
    assert lay.top_level == {}  # "pack" is not added at the document root


def test_layout_for_ignores_example_with_only_lists_of_records_elsewhere():
    # A dict whose values hold record arrays under another key is not a record.
    assert L.layout_for('x {"other": [{"a": 1}]}', doc(), "/skins") is None


def test_shape_breaks_allow_identical_skips_lost_values_only():
    lay = L.layout_for(INSTRUCTION, doc(), "/skins")
    before = doc()["skins"][:3]
    after = [{"id": "Steve", "geometry": "g", "textures": {"body": "b"}}] * 3
    strict = L.shape_breaks(before, after, [0, 1, 2], lay, "/skins")
    loose = L.shape_breaks(
        before, after, [0, 1, 2], lay, "/skins", allow_identical=True
    )
    assert any("own" in p for p in strict)
    assert loose == []
    # Structure is still checked when identical records are allowed.
    wrapped = [{"skins": [a]} for a in after]
    assert L.shape_breaks(
        before, wrapped, [0, 1, 2], lay, "/skins", allow_identical=True
    )
