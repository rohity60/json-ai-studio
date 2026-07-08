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
        assert explanation == "{not valid json at all"


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
