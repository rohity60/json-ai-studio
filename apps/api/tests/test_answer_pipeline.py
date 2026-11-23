"""Shared answer pipeline (chat turns + review batches)."""

from src.json_ai_studio.answer_pipeline import apply_guarded, expand_answer

SKINS = [{"name": f"s{i}", "geo": f"g{i}"} for i in range(6)]
EXAMPLE = 'match {"skins": [{"name": "Steve", "geo": "steve.obj"}]}'


def test_expand_answer_moves_wildcards_noops():
    doc = {"skins": SKINS}
    out = expand_answer(
        [
            {"operation": "rename", "path": "/skins/*/name", "new_key": "id"},
            {"operation": "modify", "path": "/skins/0/geo", "new_value": "g0"},
        ],
        [],
        doc,
        1000,
    )
    ops = {(d["operation"], d["path"]) for d in out.diffs}
    assert ("add", "/skins/5/id") in ops and ("delete", "/skins/5/name") in ops
    assert out.noops == 1


def test_apply_guarded_clean():
    doc = {"skins": SKINS}
    diffs = [{"operation": "modify", "path": "/skins/0/geo", "new_value": "x"}]
    res = apply_guarded(diffs, doc, "fix it")
    assert res.note is None and res.held == [] and len(res.applied) == 1


def test_apply_guarded_holds_example_values_keeps_rest():
    doc = {"skins": SKINS, "pack": None}
    diffs = [
        {"operation": "modify", "path": f"/skins/{i}/geo", "new_value": "steve.obj"}
        for i in range(6)
    ] + [{"operation": "modify", "path": "/pack", "new_value": {"v": 1}}]
    res = apply_guarded(diffs, doc, EXAMPLE)
    assert res.note and res.question
    assert len(res.held) == 6
    assert res.merged["pack"] == {"v": 1}
    assert res.merged["skins"] == SKINS


def test_apply_guarded_min_elements():
    doc = {"skins": SKINS[:3]}
    diffs = [
        {"operation": "modify", "path": f"/skins/{i}/geo", "new_value": "steve.obj"}
        for i in range(3)
    ]
    assert apply_guarded(diffs, doc, EXAMPLE).note is None
    assert apply_guarded(diffs, doc, EXAMPLE, min_elements=3).note
