"""Tests for DiffUtils apply/revert/apply_all and LLM response parsing.

Semantics under test (strict engine):
- Navigation never auto-creates parents and never writes to a fallback
  location; unresolvable paths raise DiffApplyError.
- Numeric segments index lists only when the parent is a list; dicts
  with numeric string keys stay addressable.
- add on lists inserts at index (0..len, or "-" to append); modify on
  lists requires an in-range index; delete requires the target to exist.
- Multiple deletes on the same list are applied highest-index-first.
"""

import pytest

from src.json_ai_studio.diff_utils import (
    DiffApplyError,
    DiffUtils,
    normalize_entry,
    parse_llm_response,
)

# ---------------------------------------------------------------------------
# DiffUtils.apply
# ---------------------------------------------------------------------------


class TestDiffUtilsApply:
    def test_apply_dict_modify(self):
        json_data = {"name": "old", "value": 42}
        diff = {"path": "/name", "operation": "modify", "new_value": "new"}
        result = DiffUtils.apply(diff, json_data)
        assert result["name"] == "new"
        assert result["value"] == 42
        assert json_data["name"] == "old"  # original untouched

    def test_apply_dict_add(self):
        json_data = {"name": "old"}
        diff = {"path": "/new_key", "operation": "add", "new_value": "added"}
        result = DiffUtils.apply(diff, json_data)
        assert result["new_key"] == "added"

    def test_apply_dict_modify_upserts_missing_key(self):
        """LLMs often say 'modify' when adding a new dict key."""
        json_data = {"a": 1}
        diff = {"path": "/b", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result["b"] == 2

    def test_apply_dict_delete(self):
        json_data = {"name": "old", "keep": True}
        diff = {"path": "/name", "operation": "delete"}
        result = DiffUtils.apply(diff, json_data)
        assert "name" not in result
        assert result["keep"] is True

    def test_apply_dict_delete_missing_key_raises(self):
        json_data = {"keep": True}
        diff = {"path": "/name", "operation": "delete"}
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)

    def test_apply_array_modify_in_bounds(self):
        json_data = {"items": [{"x": 1}, {"x": 2}]}
        diff = {"path": "/items/0/x", "operation": "modify", "new_value": 99}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"][0]["x"] == 99

    def test_apply_array_modify_out_of_bounds_raises(self):
        """A hallucinated index must NOT silently append elsewhere."""
        json_data = {"items": [{"x": 1}]}
        diff = {"path": "/items/5/x", "operation": "modify", "new_value": 99}
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)
        assert json_data == {"items": [{"x": 1}]}

    def test_apply_array_add_at_end(self):
        json_data = {"items": ["a"]}
        diff = {"path": "/items/1", "operation": "add", "new_value": "b"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["a", "b"]

    def test_apply_array_add_insert_middle(self):
        json_data = {"items": ["a", "c"]}
        diff = {"path": "/items/1", "operation": "add", "new_value": "b"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["a", "b", "c"]

    def test_apply_array_add_dash_appends(self):
        json_data = {"items": ["a"]}
        diff = {"path": "/items/-", "operation": "add", "new_value": "b"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["a", "b"]

    def test_apply_array_add_to_empty(self):
        json_data = {"items": []}
        diff = {"path": "/items/0", "operation": "add", "new_value": "first"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["first"]

    def test_apply_array_add_beyond_length_raises(self):
        json_data = {"items": ["a"]}
        diff = {"path": "/items/5", "operation": "add", "new_value": "b"}
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)

    def test_apply_array_delete(self):
        json_data = {"items": ["a", "b", "c"]}
        diff = {"path": "/items/1", "operation": "delete"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["a", "c"]

    def test_apply_nested_path(self):
        json_data = {"howToRedeem": [{"mode": "a", "title": "Step 1"}]}
        diff = {
            "path": "/howToRedeem/0/title",
            "operation": "modify",
            "new_value": "yellow",
        }
        result = DiffUtils.apply(diff, json_data)
        assert result["howToRedeem"][0]["title"] == "yellow"

    def test_apply_missing_intermediate_raises(self):
        """No auto-vivification: missing parents are an error, not a guess."""
        json_data = {"services": {"api": {"timeout": 30}}}
        diff = {
            "path": "/services/payment/timeout",
            "operation": "modify",
            "new_value": 60,
        }
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)

    def test_apply_scalar_parent_raises(self):
        json_data = {"a": "scalar"}
        diff = {"path": "/a/b/c", "operation": "modify", "new_value": 1}
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)

    def test_apply_numeric_dict_key(self):
        """Numeric segments address dict keys when the parent is a dict."""
        json_data = {"levels": {"0": "zero", "1": "one"}}
        diff = {"path": "/levels/1", "operation": "modify", "new_value": "uno"}
        result = DiffUtils.apply(diff, json_data)
        assert result["levels"] == {"0": "zero", "1": "uno"}

    def test_apply_escaped_slash_key(self):
        """~1 unescapes to '/' per RFC 6901."""
        json_data = {"a/b": 1}
        diff = {"path": "/a~1b", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result["a/b"] == 2

    def test_apply_escaped_tilde_key(self):
        json_data = {"a~b": 1}
        diff = {"path": "/a~0b", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result["a~b"] == 2

    def test_apply_empty_diff_is_noop_copy(self):
        json_data = {"a": 1}
        result = DiffUtils.apply({}, json_data)
        assert result == {"a": 1}
        assert result is not json_data

    def test_apply_empty_path(self):
        json_data = {"a": 1}
        diff = {"path": "", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result == {"a": 1}

    def test_apply_single_slash_path(self):
        json_data = {"a": 1}
        diff = {"path": "/", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result == {"a": 1}

    def test_apply_unknown_operation_raises(self):
        json_data = {"a": 1}
        diff = {"path": "/a", "operation": "explode", "new_value": 2}
        with pytest.raises(DiffApplyError):
            DiffUtils.apply(diff, json_data)

    def test_apply_operation_aliases(self):
        json_data = {"a": 1, "b": 2}
        result = DiffUtils.apply(
            {"path": "/a", "operation": "replace", "new_value": 9}, json_data
        )
        assert result["a"] == 9
        result = DiffUtils.apply({"path": "/b", "operation": "remove"}, json_data)
        assert "b" not in result


# ---------------------------------------------------------------------------
# DiffUtils.revert
# ---------------------------------------------------------------------------


class TestDiffUtilsRevert:
    def test_revert_dict_modify(self):
        json_data = {"name": "current"}
        diff = {"path": "/name", "operation": "modify", "old_value": "old"}
        result = DiffUtils.revert(diff, json_data)
        assert result["name"] == "old"

    def test_revert_dict_add_removes_key(self):
        json_data = {"name": "added", "keep": 1}
        diff = {"path": "/name", "operation": "add", "old_value": None}
        result = DiffUtils.revert(diff, json_data)
        assert "name" not in result
        assert result["keep"] == 1

    def test_revert_dict_delete_restores_value(self):
        json_data = {"keep": True}
        diff = {"path": "/name", "operation": "delete", "old_value": "deleted"}
        result = DiffUtils.revert(diff, json_data)
        assert result["name"] == "deleted"

    def test_revert_array_modify(self):
        json_data = {"items": [{"x": 99}]}
        diff = {"path": "/items/0/x", "operation": "modify", "old_value": 1}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"][0]["x"] == 1

    def test_revert_array_add_removes_element(self):
        json_data = {"items": [{"x": 1}, {"x": 99}]}
        diff = {"path": "/items/1", "operation": "add", "old_value": None}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == [{"x": 1}]

    def test_revert_array_add_dash_removes_last(self):
        json_data = {"items": ["a", "b"]}
        diff = {"path": "/items/-", "operation": "add"}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == ["a"]

    def test_revert_array_delete_reinserts(self):
        json_data = {"items": [{"x": 2}]}
        diff = {"path": "/items/0", "operation": "delete", "old_value": {"x": 1}}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == [{"x": 1}, {"x": 2}]

    def test_revert_out_of_bounds_raises(self):
        json_data = {"items": [{"x": 1}]}
        diff = {"path": "/items/5/x", "operation": "modify", "old_value": None}
        with pytest.raises(DiffApplyError):
            DiffUtils.revert(diff, json_data)

    def test_revert_empty_diff_is_noop_copy(self):
        json_data = {"a": 1}
        result = DiffUtils.revert({}, json_data)
        assert result == {"a": 1}
        assert result is not json_data

    def test_apply_then_revert_roundtrip(self):
        """apply followed by revert restores the original document."""
        original = {
            "services": {"api": {"timeout": 30}},
            "steps": [{"mode": "a"}, {"mode": "b"}, {"mode": "c"}],
        }
        cases = [
            {
                "path": "/services/api/timeout",
                "operation": "modify",
                "old_value": 30,
                "new_value": 60,
            },
            {
                "path": "/services/api/retries",
                "operation": "add",
                "old_value": None,
                "new_value": 5,
            },
            {
                "path": "/steps/1",
                "operation": "delete",
                "old_value": {"mode": "b"},
                "new_value": None,
            },
            {
                "path": "/steps/3",
                "operation": "add",
                "old_value": None,
                "new_value": {"mode": "d"},
            },
        ]
        for diff in cases:
            applied = DiffUtils.apply(diff, original)
            assert applied != original
            reverted = DiffUtils.revert(diff, applied)
            assert reverted == original, f"roundtrip failed for {diff['path']}"


# ---------------------------------------------------------------------------
# DiffUtils.apply_all / apply_all_verbose
# ---------------------------------------------------------------------------


class TestApplyAll:
    def test_multi_delete_same_array_index_shift(self):
        """Deleting indices 1 and 3 must remove the intended elements."""
        json_data = {"items": ["a", "b", "c", "d", "e"]}
        diffs = [
            {"path": "/items/1", "operation": "delete"},
            {"path": "/items/3", "operation": "delete"},
        ]
        result = DiffUtils.apply_all(diffs, json_data)
        assert result["items"] == ["a", "c", "e"]

    def test_multi_delete_already_descending(self):
        json_data = {"items": ["a", "b", "c", "d"]}
        diffs = [
            {"path": "/items/3", "operation": "delete"},
            {"path": "/items/0", "operation": "delete"},
        ]
        result = DiffUtils.apply_all(diffs, json_data)
        assert result["items"] == ["b", "c"]

    def test_delete_then_modify_same_array_stale_index(self):
        """Regression: a delete at a low index must not invalidate a
        modify at a higher original index that follows it in the diff
        list. Both indices are computed against the same original
        5-element array; the delete at 0 must not shift the modify's
        target before it runs."""
        json_data = {"items": ["a", "b", "c", "d", "e"]}
        diffs = [
            {"path": "/items/0", "operation": "delete"},
            {"path": "/items/4", "operation": "modify", "new_value": "E"},
        ]
        result, applied, failed = DiffUtils.apply_all_verbose(diffs, json_data)
        assert failed == []
        assert len(applied) == 2
        assert result["items"] == ["b", "c", "d", "E"]

    def test_many_deletes_then_modify_same_array_stale_index(self):
        """Same bug at the scale seen in production: several low-index
        deletes ahead of a modify at a much higher original index."""
        json_data = {"items": [f"v{i}" for i in range(10)]}
        diffs = [
            {"path": "/items/1", "operation": "delete"},
            {"path": "/items/2", "operation": "delete"},
            {"path": "/items/3", "operation": "delete"},
            {"path": "/items/9", "operation": "modify", "new_value": "V9"},
        ]
        result, applied, failed = DiffUtils.apply_all_verbose(diffs, json_data)
        assert failed == []
        assert len(applied) == 4
        assert result["items"] == ["v0", "v4", "v5", "v6", "v7", "v8", "V9"]

    def test_delete_then_add_same_array_stale_index(self):
        """An insert at a higher original index must not be shifted out
        from under itself by an earlier-processed lower-index delete."""
        json_data = {"items": ["a", "b", "c", "d"]}
        diffs = [
            {"path": "/items/0", "operation": "delete"},
            {"path": "/items/3", "operation": "add", "new_value": "X"},
        ]
        result, applied, failed = DiffUtils.apply_all_verbose(diffs, json_data)
        assert failed == []
        assert result["items"] == ["b", "c", "X", "d"]

    def test_mixed_ops_batch(self):
        json_data = {
            "services": {"api": {"timeout": 30}, "worker": {"timeout": 10}},
            "flags": ["x"],
        }
        diffs = [
            {"path": "/services/api/timeout", "operation": "modify", "new_value": 60},
            {"path": "/services/api/retries", "operation": "add", "new_value": 3},
            {"path": "/services/worker", "operation": "delete"},
            {"path": "/flags/1", "operation": "add", "new_value": "y"},
        ]
        result = DiffUtils.apply_all(diffs, json_data)
        assert result == {
            "services": {"api": {"timeout": 60, "retries": 3}},
            "flags": ["x", "y"],
        }

    def test_verbose_reports_failures_without_mutating(self):
        json_data = {"a": {"b": 1}}
        diffs = [
            {"path": "/a/b", "operation": "modify", "new_value": 2},
            {"path": "/missing/deep", "operation": "modify", "new_value": 3},
        ]
        result, applied, failed = DiffUtils.apply_all_verbose(diffs, json_data)
        assert result == {"a": {"b": 2}}
        assert len(applied) == 1
        assert len(failed) == 1
        assert failed[0][0]["path"] == "/missing/deep"

    def test_empty_list_returns_copy(self):
        json_data = {"a": 1}
        result = DiffUtils.apply_all([], json_data)
        assert result == {"a": 1}
        assert result is not json_data


# ---------------------------------------------------------------------------
# Snapshot index ordering (several ops on one list, mixed add/delete)
# Every index refers to the document BEFORE the answer (prompt rule 4).
# ---------------------------------------------------------------------------


def _add(path, v):
    return {"path": path, "operation": "add", "old_value": None, "new_value": v}


def _del(path, v):
    return {"path": path, "operation": "delete", "old_value": v, "new_value": None}


def _mod(path, old, new):
    return {"path": path, "operation": "modify", "old_value": old, "new_value": new}


ABCD = {"items": ["A", "B", "C", "D"]}

SNAPSHOT_CASES = [
    # (id, diffs, expected items)
    (
        "prod_off_by_one_append_run",
        [_add(f"/items/{i}", v) for i, v in zip(range(3, 7), "WXYZ")],
        list("ABCDWXYZ"),
    ),
    (
        "sequential_append_run_from_len",
        [_add("/items/4", "X"), _add("/items/5", "Y")],
        list("ABCDXY"),
    ),
    (
        "two_appends_dash",
        [_add("/items/-", "X"), _add("/items/-", "Y")],
        list("ABCDXY"),
    ),
    (
        "two_inserts_same_gap",
        [_add("/items/1", "X"), _add("/items/1", "Y")],
        list("AXYBCD"),
    ),
    (
        "three_inserts_same_gap",
        [_add("/items/1", "X"), _add("/items/1", "Y"), _add("/items/1", "Z")],
        list("AXYZBCD"),
    ),
    (
        "inserts_in_two_gaps",
        [_add("/items/1", "X"), _add("/items/3", "Y")],
        list("AXBCYD"),
    ),
    ("delete_two", [_del("/items/0", "A"), _del("/items/2", "C")], list("BD")),
    (
        "insert_then_delete_later",
        [_add("/items/1", "X"), _del("/items/2", "C")],
        list("AXBD"),
    ),
    (
        "delete_then_insert_later",
        [_del("/items/1", "B"), _add("/items/3", "X")],
        list("ACXD"),
    ),
    (
        "replace_delete_add_same_index",
        [_del("/items/2", "C"), _add("/items/2", "X")],
        list("ABXD"),
    ),
    (
        "replace_add_before_delete_same_index",
        [_add("/items/2", "X"), _del("/items/2", "C")],
        list("ABXD"),
    ),
    (
        "delete_then_modify_later",
        [_del("/items/1", "B"), _mod("/items/2", "C", "C2")],
        list(["A", "C2", "D"]),
    ),
    (
        "modify_and_insert_same_index",
        [_add("/items/2", "X"), _mod("/items/2", "C", "C2")],
        list(["A", "B", "X", "C2", "D"]),
    ),
    (
        "delete_then_append_dash",
        [_del("/items/1", "B"), _add("/items/-", "X")],
        list("ACDX"),
    ),
    (
        "sequential_mid_run_past_end",
        [
            _add("/items/2", "X"),
            _add("/items/3", "Y"),
            _add("/items/4", "Z"),
            _add("/items/5", "W"),
        ],
        list("ABXYZWCD"),
    ),
]


class TestSnapshotOrdering:
    @pytest.mark.parametrize(
        "diffs,expected",
        [c[1:] for c in SNAPSHOT_CASES],
        ids=[c[0] for c in SNAPSHOT_CASES],
    )
    def test_case(self, diffs, expected):
        result, applied, failed = DiffUtils.apply_all_verbose(diffs, ABCD)
        assert failed == []
        assert len(applied) == len(diffs)
        assert result["items"] == expected

    def test_applied_returned_in_model_order(self):
        diffs = [_add("/items/1", "X"), _add("/items/3", "Y"), _del("/items/0", "A")]
        _, applied, _ = DiffUtils.apply_all_verbose(diffs, ABCD)
        assert [d["path"] for d in applied] == ["/items/1", "/items/3", "/items/0"]

    def test_append_run_paths_rewritten_to_dash(self):
        diffs = [_add(f"/items/{i}", v) for i, v in zip(range(3, 7), "WXYZ")]
        _, applied, _ = DiffUtils.apply_all_verbose(diffs, ABCD)
        assert [d["model_path"] for d in applied] == ["/items/-"] * 4
        assert [d["path"] for d in applied] == [f"/items/{i}" for i in range(4, 8)]

    def test_two_adds_len_minus_one_and_len_stay_snapshot(self):
        """{len-1, len} is valid snapshot input: X before D, Y at the end."""
        diffs = [_add("/items/3", "X"), _add("/items/4", "Y")]
        result, _, failed = DiffUtils.apply_all_verbose(diffs, ABCD)
        assert failed == []
        assert result["items"] == list("ABCXDY")

    def test_single_add_past_end_still_fails(self):
        """A lone out-of-range index is a hallucination, not an append."""
        result, applied, failed = DiffUtils.apply_all_verbose(
            [_add("/items/9", "X")], ABCD
        )
        assert applied == []
        assert "out of range" in failed[0][1]
        assert result == ABCD

    def test_nested_modify_sorted_with_its_element(self):
        doc = {"cards": [{"t": "a"}, {"t": "b"}, {"t": "c"}]}
        diffs = [
            _del("/cards/0", {"t": "a"}),
            _mod("/cards/2/t", "c", "C"),
            _add("/cards/1", {"t": "x"}),
        ]
        result, _, failed = DiffUtils.apply_all_verbose(diffs, doc)
        assert failed == []
        assert result["cards"] == [{"t": "x"}, {"t": "b"}, {"t": "C"}]

    def test_nested_list_inside_element(self):
        doc = {"cards": [{"tags": ["a", "b"]}, {"tags": ["c"]}]}
        diffs = [
            _del("/cards/0", {"tags": ["a", "b"]}),
            _add("/cards/1/tags/-", "d"),
            _add("/cards/1/tags/0", "z"),
        ]
        result, _, failed = DiffUtils.apply_all_verbose(diffs, doc)
        assert failed == []
        assert result["cards"] == [{"tags": ["z", "c", "d"]}]

    def test_dict_ops_keep_model_order(self):
        doc = {"a": {}}
        diffs = [_add("/a/b", {}), _add("/a/b/c", 1)]
        result, _, failed = DiffUtils.apply_all_verbose(diffs, doc)
        assert failed == []
        assert result == {"a": {"b": {"c": 1}}}


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------


class TestParseLlmResponse:
    def test_bare_array(self):
        text = '[{"path": "/a", "operation": "modify", "old_value": 1, "new_value": 2}]'
        diffs, explanation = parse_llm_response(text)
        assert diffs == [
            {"path": "/a", "operation": "modify", "old_value": 1, "new_value": 2}
        ]
        assert explanation == ""

    def test_object_with_diffs_and_explanation(self):
        text = (
            '{"diffs": [{"path": "/a", "operation": "add", "old_value": null,'
            ' "new_value": 5}], "explanation": "Added a."}'
        )
        diffs, explanation = parse_llm_response(text)
        assert len(diffs) == 1
        assert diffs[0]["operation"] == "add"
        assert explanation == "Added a."

    def test_fenced_json_with_language_tag(self):
        text = '```json\n[{"path": "/a", "operation": "delete"}]\n```'
        diffs, _ = parse_llm_response(text)
        assert len(diffs) == 1
        assert diffs[0]["operation"] == "delete"

    def test_fenced_json_without_language_tag(self):
        text = '```\n{"diffs": [], "explanation": "nothing to do"}\n```'
        diffs, explanation = parse_llm_response(text)
        assert diffs == []
        assert explanation == "nothing to do"

    def test_empty_array_with_trailing_prose(self):
        """The old Example-3 style: [] followed by an explanation."""
        text = "[]\nExplanation: No element has mode='b'. Did you mean 'c'?"
        diffs, explanation = parse_llm_response(text)
        assert diffs == []
        assert "mode='b'" in explanation

    def test_prose_before_json(self):
        text = 'Here is the change:\n[{"path": "/a", "operation": "modify", "new_value": 1}]'
        diffs, explanation = parse_llm_response(text)
        assert len(diffs) == 1
        assert "Here is the change:" in explanation

    def test_plain_text_only(self):
        text = "I cannot modify that field because it does not exist."
        diffs, explanation = parse_llm_response(text)
        assert diffs == []
        assert explanation == text

    def test_empty_and_none(self):
        assert parse_llm_response("") == ([], "")
        assert parse_llm_response(None) == ([], "")

    def test_single_entry_object(self):
        text = '{"path": "/a", "operation": "modify", "new_value": 2}'
        diffs, _ = parse_llm_response(text)
        assert diffs == [
            {"path": "/a", "operation": "modify", "old_value": None, "new_value": 2}
        ]

    def test_op_and_value_aliases(self):
        text = '[{"path": "/a", "op": "replace", "value": 7}]'
        diffs, _ = parse_llm_response(text)
        assert diffs == [
            {"path": "/a", "operation": "modify", "old_value": None, "new_value": 7}
        ]

    def test_key_instead_of_path(self):
        text = '[{"key": "a.b", "op": "set", "value": 1}]'
        diffs, _ = parse_llm_response(text)
        assert diffs[0]["path"] == "/a/b"
        assert diffs[0]["operation"] == "modify"

    def test_invalid_entries_dropped(self):
        text = '[{"path": "/a", "operation": "modify", "new_value": 1}, {"nonsense": true}, 42]'
        diffs, _ = parse_llm_response(text)
        assert len(diffs) == 1

    def test_garbage_json_like_text(self):
        diffs, explanation = parse_llm_response("{not valid json at all")
        assert diffs == []
        # JSON-looking but unparseable output gets a friendly message, never
        # raw model JSON (df8a7b8).
        assert "couldn't apply that cleanly" in explanation


class TestNormalizeEntry:
    def test_path_gets_leading_slash(self):
        entry = normalize_entry({"path": "a/b", "operation": "modify", "new_value": 1})
        assert entry["path"] == "/a/b"

    def test_rejects_missing_operation(self):
        assert normalize_entry({"path": "/a", "new_value": 1}) is None

    def test_rejects_non_dict(self):
        assert normalize_entry("nope") is None
        assert normalize_entry(None) is None


class TestParseRepair:
    def test_trailing_comma_in_object_and_array(self):
        text = '{"diffs": [{"path": "/a", "operation": "modify", "new_value": 1,},], "explanation": "ok",}'
        diffs, explanation = parse_llm_response(text)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "/a"
        assert explanation == "ok"

    def test_trailing_comma_in_bare_array(self):
        text = '[{"path": "/a", "operation": "delete"},]'
        diffs, _ = parse_llm_response(text)
        assert len(diffs) == 1


# ---------------------------------------------------------------------------
# Truncation guard (edit-safety ES-01..07)
# ---------------------------------------------------------------------------

from src.json_ai_studio.diff_utils import TRUNCATION_REASON  # noqa: E402
from src.json_ai_studio.preview import (  # noqa: E402
    ELLIPSIS,
    TRUNCATED_SUFFIX,
    ends_with_preview_marker,
)

_LONG = (
    "Elara is a Wolf-kinn ranger from the northern woods who guards the old shrine. "
    + " ".join(
        f"In year {y} the {w} clan of {p} sent {y % 7 + 2} envoys to trade {g} for salt."
        for y, w, p, g in zip(
            range(1100, 1160),
            ["wolf", "owl", "elk", "fox", "bear", "hawk"] * 10,
            [
                "Tarn",
                "Velm",
                "Oskar",
                "Brin",
                "Hale",
                "Mora",
                "Kest",
                "Ulva",
                "Dun",
                "Rys",
            ]
            * 6,
            ["amber", "furs", "iron", "wool", "honey"] * 12,
        )
    )
)


def _apply_one_verbose(diff, doc):
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    return result, applied, failed


class TestTruncationGuard:
    def test_preview_with_marker_rejected(self):
        doc = {"data": {"description": _LONG}}
        preview = _LONG[:80].replace("Wolf-kinn", "Wolf-kin") + ELLIPSIS
        diff = {
            "path": "/data/description",
            "operation": "modify",
            "new_value": preview,
        }
        result, applied, failed = _apply_one_verbose(diff, doc)
        assert applied == []
        assert [(d["path"], d["new_value"], r) for d, r in failed] == [
            (diff["path"], diff["new_value"], TRUNCATION_REASON)
        ]
        assert result["data"]["description"] == _LONG

    def test_edited_preview_without_marker_rejected(self):
        # Repro 2026-11-10: 7485 → 80 chars, marker dropped by the model.
        doc = {"d": _LONG}
        new = _LONG[:80].replace("Wolf-kinn", "Wolf-kin")
        _, applied, failed = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": new}, doc
        )
        assert applied == [] and failed[0][1] == TRUNCATION_REASON

    def test_tool_result_marker_rejected(self):
        doc = {"d": _LONG}
        new = _LONG[:3000] + TRUNCATED_SUFFIX
        _, applied, failed = _apply_one_verbose(
            {"path": "/d", "operation": "replace", "new_value": new}, doc
        )
        assert applied == [] and failed[0][1] == TRUNCATION_REASON

    def test_nested_preview_leaf_rejected(self):
        # ES-02: whole entry rewritten; untouched long sibling copied from preview.
        doc = {"entries": [{"name": "Elara", "content": _LONG}]}
        new_entry = {"name": "Elara Moon", "content": _LONG[:80]}
        _, applied, failed = _apply_one_verbose(
            {"path": "/entries/0", "operation": "modify", "new_value": new_entry}, doc
        )
        assert applied == [] and failed[0][1] == TRUNCATION_REASON

    def test_full_rewrite_of_long_string_allowed(self):
        doc = {"d": _LONG}
        new = _LONG.replace("Wolf-kinn", "Wolf-kin")
        result, applied, _ = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": new}, doc
        )
        assert applied and result["d"] == new

    def test_heavily_edited_partial_rewrite_rejected(self):
        # Live repro 2026-11-10: model rewrote the first 4000 chars it could
        # read (typos fixed, "…" turned into "...)"), dropped the rest.
        doc = {"d": _LONG}
        part = _LONG[: len(_LONG) // 2]
        new = (
            part.replace("Wolf-kinn", "Wolf-kin")
            .replace("northern", "Northern")
            .replace(" the ", " The ")
            + "...)"
        )
        _, applied, failed = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": new}, doc
        )
        assert applied == [] and failed[0][1] == TRUNCATION_REASON

    def test_exact_prefix_cut_rejected(self):
        doc = {"d": _LONG}
        _, applied, failed = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": _LONG[:100]}, doc
        )
        assert applied == [] and failed[0][1] == TRUNCATION_REASON

    def test_condensed_rewrite_ending_like_old_allowed(self):
        old = "".join(f"Paragraph {i}: the ranger walks the path. " for i in range(60))
        new = "Summary: rangers walk. " + old[-200:]
        result, applied, _ = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": new}, {"d": old}
        )
        assert applied and result["d"] == new

    def test_new_summary_text_allowed(self):
        doc = {"d": _LONG}
        result, applied, _ = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": "A ranger."}, doc
        )
        assert applied and result["d"] == "A ranger."

    def test_ellipsis_allowed_when_not_shorter_or_new_path(self):
        # ES-04
        doc = {"short": "Wait"}
        result, applied, _ = DiffUtils.apply_all_verbose(
            [
                {"path": "/short", "operation": "modify", "new_value": "Wait for it…"},
                {"path": "/fresh", "operation": "add", "new_value": "To be continued…"},
            ],
            doc,
        )
        assert len(applied) == 2
        assert result["short"] == "Wait for it…"

    def test_short_old_value_not_guarded_without_marker(self):
        doc = {"d": "Hello there world"}
        result, applied, _ = _apply_one_verbose(
            {"path": "/d", "operation": "modify", "new_value": "Hello"}, doc
        )
        assert applied and result["d"] == "Hello"

    def test_delete_unaffected(self):
        doc = {"d": _LONG}
        result, applied, _ = _apply_one_verbose(
            {"path": "/d", "operation": "delete"}, doc
        )
        assert applied and "d" not in result

    def test_markers(self):
        assert ends_with_preview_marker("abc…")
        assert ends_with_preview_marker("x…(truncated)")
        assert ends_with_preview_marker("…+700 more items")
        assert not ends_with_preview_marker("abc.")


class TestIndexRepair:
    """normalise_diffs: server-side repair of model indices (live evals
    2026-11-23)."""

    CARDS = {"cards": [{"name": n} for n in "ABCD"]}

    def _run(self, diffs, doc=None):
        return DiffUtils.apply_all_verbose(diffs, doc or self.CARDS)

    def test_sequential_deletes_retargeted_by_old_value(self):
        """nvidia: delete A at 0, then C at 1 (numbered after deleting A)."""
        result, applied, failed = self._run(
            [_del("/cards/0", {"name": "A"}), _del("/cards/1", {"name": "C"})]
        )
        assert failed == []
        assert [c["name"] for c in result["cards"]] == ["B", "D"]
        assert [d["path"] for d in applied] == ["/cards/0", "/cards/2"]

    def test_nested_modify_retargeted_by_old_value(self):
        """nvidia: delete B at 1, rename C via /cards/1/name (old 'C')."""
        result, _, failed = self._run(
            [_del("/cards/1", {"name": "B"}), _mod("/cards/1/name", "C", "C2")]
        )
        assert failed == []
        assert [c["name"] for c in result["cards"]] == ["A", "C2", "D"]

    def test_ambiguous_old_value_not_retargeted(self):
        doc = {"items": ["x", "y", "x"]}
        result, _, _ = self._run([_mod("/items/1", "x", "z")], doc)
        assert result["items"] == ["x", "z", "x"]

    def test_matching_old_value_kept(self):
        result, applied, _ = self._run([_mod("/cards/2/name", "C", "C2")])
        assert applied[0]["path"] == "/cards/2/name"
        assert result["cards"][2]["name"] == "C2"

    def test_restated_shifted_elements_dropped(self):
        """nvidia: insert N at 2 plus 'modify' C/D at 3/4 with new == old."""
        result, applied, failed = self._run(
            [
                _add("/cards/2", {"name": "N"}),
                _mod("/cards/3", {"name": "C"}, {"name": "C"}),
                _mod("/cards/4", {"name": "D"}, {"name": "D"}),
            ]
        )
        assert failed == []
        assert len(applied) == 1
        assert [c["name"] for c in result["cards"]] == list("ABNCD")

    def test_star_add_becomes_append(self):
        """gemma4: 'add /roles/*' for new roles."""
        result, applied, failed = self._run([_add("/cards/*", {"name": "X"})])
        assert failed == []
        assert applied[0]["model_path"] == "/cards/-"
        assert applied[0]["path"] == "/cards/4"
        assert result["cards"][-1] == {"name": "X"}

    def test_append_stored_with_concrete_path(self):
        _, applied, _ = self._run(
            [_add("/cards/-", {"name": "X"}), _add("/cards/-", {"name": "Y"})]
        )
        assert [d["path"] for d in applied] == ["/cards/4", "/cards/5"]
        assert [d["model_path"] for d in applied] == ["/cards/-", "/cards/-"]
        assert [d["preview_path"] for d in applied] == ["/cards/4", "/cards/5"]

    def test_modify_path_one_level_too_high_is_deepened(self):
        """gemma4: modify /cards/2 old 'C' new 'C2' meant /cards/2/name."""
        doc = {"cards": [{"name": n, "text": "t"} for n in "ABCD"]}
        result, applied, failed = DiffUtils.apply_all_verbose(
            [_del("/cards/1", {"name": "B", "text": "t"}), _mod("/cards/2", "C", "C2")],
            doc,
        )
        assert failed == []
        assert applied[1]["path"] == "/cards/2/name"
        assert [c["name"] for c in result["cards"]] == ["A", "C2", "D"]

    def test_scalar_replacing_object_without_matching_key_untouched(self):
        doc = {"cards": [{"name": "A"}]}
        result, applied, _ = DiffUtils.apply_all_verbose(
            [_mod("/cards/0", "zzz", "x")], doc
        )
        assert applied[0]["path"] == "/cards/0"
        assert result["cards"] == ["x"]


class TestPreviewPathAndCheckedRevert:
    """Reject removes the element the diff produced, never just the last
    one (2026-11-23: rejecting an append popped a different item)."""

    DOC = {"steps": list("ABCD")}

    def test_preview_path_accounts_for_later_ops(self):
        diffs = [_add("/steps/1", "X"), _add("/steps/3", "Y"), _del("/steps/0", "A")]
        result, applied, _ = DiffUtils.apply_all_verbose(diffs, self.DOC)
        assert result["steps"] == list("XBCYD")
        for d in applied[:2]:
            at = int(d["preview_path"].rsplit("/", 1)[1])
            assert result["steps"][at] == d["new_value"]

    @pytest.mark.parametrize("reject", ["X", "Y", "Z"])
    def test_reject_one_of_three_appends(self, reject):
        diffs = [_add("/steps/-", v) for v in "XYZ"]
        doc, applied, _ = DiffUtils.apply_all_verbose(diffs, self.DOC)
        target = next(d for d in applied if d["new_value"] == reject)
        out = DiffUtils.revert_checked(target, doc)
        assert out["steps"] == [*"ABCD", *[v for v in "XYZ" if v != reject]]

    def test_reject_after_earlier_reject_relocates(self):
        diffs = [_add("/steps/-", v) for v in "XYZ"]
        doc, applied, _ = DiffUtils.apply_all_verbose(diffs, self.DOC)
        doc = DiffUtils.revert_checked(applied[0], doc)  # X gone, Z shifted
        doc = DiffUtils.revert_checked(applied[2], doc)
        assert doc["steps"] == [*"ABCD", "Y"]

    def test_reject_refuses_when_element_gone(self):
        doc = {"steps": list("ABCD")}
        with pytest.raises(DiffApplyError):
            DiffUtils.revert_checked(
                {
                    "path": "/steps/4",
                    "operation": "add",
                    "new_value": "Q",
                    "preview_path": "/steps/4",
                },
                doc,
            )

    def test_accept_form_keeps_dash(self):
        _, applied, _ = DiffUtils.apply_all_verbose([_add("/steps/-", "X")], self.DOC)
        assert DiffUtils.accept_form(applied[0])["path"] == "/steps/-"


class TestMergedEntries:
    """nvidia nemotron 2026-11-23: several entries run together in ONE
    object with repeated keys; plain json keeps only the last."""

    ROLE = '"path": "/roles/-", "operation": "add", "old_value": null, "new_value": {"name": "%s"}'

    def test_merged_entries_split(self):
        names = ["Senior Staff", "Recruitment Staff", "Event Staff"]
        text = (
            '{"diffs": [{' + ", ".join(self.ROLE % n for n in names) + "}], "
            '"explanation": "Added three roles."}'
        )
        diffs, explanation = parse_llm_response(text)
        assert [d["new_value"]["name"] for d in diffs] == names
        assert explanation == "Added three roles."

    def test_merged_entries_split_in_salvage(self):
        text = '{"diffs": [{' + self.ROLE % "A" + ", " + self.ROLE % "B" + "}, oops]}"
        diffs, _ = parse_llm_response(text)
        assert [d["new_value"]["name"] for d in diffs] == ["A", "B"]

    def test_ordinary_objects_untouched(self):
        diffs, _ = parse_llm_response(
            '{"diffs": [{"path": "/a", "operation": "modify", "old_value": 1, '
            '"new_value": {"path": "x", "k": 1}}], "explanation": "e"}'
        )
        assert diffs == [
            {
                "path": "/a",
                "operation": "modify",
                "old_value": 1,
                "new_value": {"path": "x", "k": 1},
            }
        ]


def test_from_marker_in_plain_modify_is_resolved():
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"skins": [{"localization_name": "Target", "geometry": "geometry.a9"}]}
    diff = {
        "path": "/skins/0",
        "operation": "modify",
        "old_value": doc["skins"][0],
        "new_value": {
            "id": {"$from": "localization_name"},
            "geometry": {"$from": "geometry"},
            "textures": {"body": {"$from": "geometry"}},
        },
    }
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not failed
    assert result["skins"][0] == {
        "id": "Target",
        "geometry": "geometry.a9",
        "textures": {"body": "geometry.a9"},
    }


def test_unresolved_from_marker_is_refused_not_applied():
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"skins": [{"a": 1}]}
    diff = {
        "path": "/skins/0",
        "operation": "modify",
        "old_value": {"a": 1},
        "new_value": {"id": {"$from": "nope"}},
    }
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not applied and len(failed) == 1
    assert result == doc


def test_from_marker_on_leaf_path_reads_sibling_field():
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"skins": [{"n": "A", "g": "ga"}, {"n": "B", "g": "gb"}]}
    diffs = [
        {"path": "/skins/1/id", "operation": "add", "new_value": {"$from": "n"}},
        {
            "path": "/skins/0/g",
            "operation": "modify",
            "old_value": "ga",
            "new_value": {"$from": "n"},
        },
    ]
    result, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert not failed
    assert result["skins"] == [{"n": "A", "g": "A"}, {"n": "B", "g": "gb", "id": "B"}]


def test_from_marker_follows_old_value_retarget():
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"skins": [{"n": "A"}, {"n": "B"}]}
    diff = {
        "path": "/skins/0",  # wrong index; old_value names skin B
        "operation": "modify",
        "old_value": {"n": "B"},
        "new_value": {"id": {"$from": "n"}, "tags": [{"$from": "n"}]},
    }
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not failed
    assert result["skins"] == [{"n": "A"}, {"id": "B", "tags": ["B"]}]


def test_from_marker_never_reads_past_its_array_element():
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"name": "root", "skins": [{"n": "A"}]}
    diff = {"path": "/skins/0/id", "operation": "add", "new_value": {"$from": "name"}}
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not applied and len(failed) == 1
    assert result == doc


def test_add_into_missing_parent_creates_it_and_merges():
    doc = {"skins": [{"texture": "a0.png", "arm": "arm0.png"}]}
    diffs = [
        {"path": "/skins/0/textures/body", "operation": "add", "new_value": "a0.png"},
        {"path": "/skins/0/textures/arm", "operation": "add", "new_value": "arm0.png"},
        {"path": "/skins/0/texture", "operation": "delete", "old_value": "a0.png"},
        {"path": "/skins/0/arm", "operation": "delete", "old_value": "arm0.png"},
    ]
    result, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert not failed
    assert result == {"skins": [{"textures": {"body": "a0.png", "arm": "arm0.png"}}]}
    assert [d["path"] for d in applied if d["operation"] == "add"] == [
        "/skins/0/textures"
    ]


def test_add_merges_into_models_own_parent_add():
    doc = {"a": {}}
    diffs = [
        {"path": "/a/b", "operation": "add", "new_value": {"x": 1}},
        {"path": "/a/b/y", "operation": "add", "new_value": 2},
    ]
    result, _, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert not failed and result == {"a": {"b": {"x": 1, "y": 2}}}


def test_add_missing_array_index_parent_still_fails():
    doc = {"a": {}}
    diff = {"path": "/a/list/0/x", "operation": "add", "new_value": 1}
    result, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not applied and len(failed) == 1 and result == doc


def test_delete_held_when_move_half_fails():
    doc = {"skins": [{"texture": "a0.png", "type": "free"}]}
    diffs = [
        # add fails: unresolvable $from; its paired delete must not apply
        {
            "path": "/skins/0/textures",
            "operation": "add",
            "new_value": {"body": {"$from": "nope"}},
        },
        {"path": "/skins/0/texture", "operation": "delete", "old_value": "a0.png"},
        {"path": "/other", "operation": "add", "new_value": 1},
    ]
    result, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert result == {"skins": [{"texture": "a0.png", "type": "free"}], "other": 1}
    assert [d["path"] for d in applied] == ["/other"]
    assert len(failed) == 2


def test_absolute_from_pointer_resolves_against_document():
    doc = {"skins": [{"texture": "a0.png"}, {"texture": "a1.png"}]}
    diff = {
        "path": "/skins/1/textures",
        "operation": "add",
        "new_value": {"body": {"$from": "/skins/1/texture"}},
    }
    result, _, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not failed
    assert result["skins"][1]["textures"] == {"body": "a1.png"}


def test_from_pointer_with_star_binds_to_diff_element():
    doc = {"skins": [{"texture": "a0.png"}, {"texture": "a1.png"}]}
    diffs = [
        {
            "path": f"/skins/{i}/textures",
            "operation": "add",
            "new_value": {"body": {"$from": "/skins/*/texture"}},
        }
        for i in range(2)
    ]
    result, _, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert not failed
    assert [s["textures"]["body"] for s in result["skins"]] == ["a0.png", "a1.png"]


def test_modify_without_old_value_rejects_back_to_record():
    # Regression 2026-11-23: old_value None → reject wrote null over the record.
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"s": [{"n": "A"}, {"n": "B"}]}
    diff = {"path": "/s/1", "operation": "modify", "new_value": {"id": "B"}}
    merged, applied, failed = DiffUtils.apply_all_verbose([diff], doc)
    assert not failed and applied[0]["old_value"] == {"n": "B"}
    assert DiffUtils.revert(applied[0], merged) == doc


def test_numeric_string_over_number_keeps_type():
    # Live eval 2026-11-24: "0.0" (string) written over the float 8.0.
    from src.json_ai_studio.diff_utils import DiffUtils

    doc = {"f": 8.0, "n": 3, "b": True, "s": "x", "big": 5}
    diffs = [
        {"path": "/f", "operation": "modify", "new_value": "0.0"},
        {"path": "/n", "operation": "modify", "new_value": "7"},
        {"path": "/b", "operation": "modify", "new_value": "false"},
        {"path": "/s", "operation": "modify", "new_value": "9"},  # was a string
        {"path": "/big", "operation": "modify", "new_value": "5 seconds"},
    ]
    merged, applied, failed = DiffUtils.apply_all_verbose(diffs, doc)
    assert not failed
    assert merged == {"f": 0.0, "n": 7, "b": False, "s": "9", "big": "5 seconds"}
    assert isinstance(merged["f"], float) and isinstance(merged["n"], int)


def test_decimal_string_over_int_becomes_float():
    # Deliberate: "7.5" over an int keeps it numeric (a float), not a string.
    from src.json_ai_studio.diff_utils import DiffUtils

    merged, _, failed = DiffUtils.apply_all_verbose(
        [{"path": "/n", "operation": "modify", "new_value": "7.5"}], {"n": 3}
    )
    assert not failed and merged == {"n": 7.5} and isinstance(merged["n"], float)
