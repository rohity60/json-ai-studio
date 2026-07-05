"""Tests for DiffUtils — apply and revert diff operations.

Tests cover both dict and array operations. Dict tests pass against the
current dict-only implementation. Array tests validate the array-aware
refactor.
"""

import pytest
from src.json_ai_studio.diff_utils import DiffUtils


# ---------------------------------------------------------------------------
# DiffUtils.apply tests
# ---------------------------------------------------------------------------


class TestDiffUtilsApply:
    """Tests for DiffUtils.apply()."""

    def test_apply_dict_modify(self):
        """Modify an existing dict key."""
        json_data = {"name": "old", "value": 42}
        diff = {"path": "/name", "operation": "modify", "new_value": "new"}
        result = DiffUtils.apply(diff, json_data)
        assert result["name"] == "new"
        assert result["value"] == 42

    def test_apply_dict_add(self):
        """Add a new dict key."""
        json_data = {"name": "old"}
        diff = {"path": "/new_key", "operation": "modify", "new_value": "added"}
        result = DiffUtils.apply(diff, json_data)
        assert result["new_key"] == "added"

    def test_apply_dict_delete(self):
        """Delete an existing dict key."""
        json_data = {"name": "old", "keep": True}
        diff = {"path": "/name", "operation": "delete"}
        result = DiffUtils.apply(diff, json_data)
        assert "name" not in result
        assert result["keep"] is True

    def test_apply_array_modify_in_bounds(self):
        """Modify element at a valid array index."""
        json_data = {"items": [{"x": 1}, {"x": 2}]}
        diff = {"path": "/items/0/x", "operation": "modify", "new_value": 99}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"][0]["x"] == 99

    def test_apply_array_modify_out_of_bounds(self):
        """Modify element beyond array length — should append."""
        json_data = {"items": [{"x": 1}]}
        diff = {"path": "/items/5/x", "operation": "modify", "new_value": 99}
        result = DiffUtils.apply(diff, json_data)
        # With array-aware fix: appends {"x": 99}
        assert len(result["items"]) == 2
        assert result["items"][1]["x"] == 99

    def test_apply_array_add(self):
        """Append to an empty array."""
        json_data = {"items": []}
        diff = {"path": "/items/0", "operation": "modify", "new_value": "first"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["first"]

    def test_apply_array_delete(self):
        """Delete an array element by index."""
        json_data = {"items": ["a", "b", "c"]}
        diff = {"path": "/items/1", "operation": "delete"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"] == ["a", "c"]

    def test_apply_nested_path(self):
        """Navigate dict → array → field."""
        json_data = {"howToRedeem": [{"mode": "a", "title": "Step 1"}]}
        diff = {"path": "/howToRedeem/0/title", "operation": "modify", "new_value": "yellow"}
        result = DiffUtils.apply(diff, json_data)
        assert result["howToRedeem"][0]["title"] == "yellow"

    def test_apply_empty_diffs(self):
        """Empty diff list returns a deep copy."""
        json_data = {"a": 1}
        result = DiffUtils.apply({}, json_data)
        assert result == {"a": 1}
        assert result is not json_data

    def test_apply_nonexistent_key(self):
        """Add a key that does not exist in dict."""
        json_data = {"a": 1}
        diff = {"path": "/b", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result["b"] == 2

    def test_apply_array_non_digit_target(self):
        """Path like /items/0/title where parent is list, target is string."""
        json_data = {"items": [{"x": 1}]}
        diff = {"path": "/items/0/title", "operation": "modify", "new_value": "added"}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"][0]["title"] == "added"

    def test_apply_empty_path(self):
        """Empty path returns unchanged copy."""
        json_data = {"a": 1}
        diff = {"path": "", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result == {"a": 1}

    def test_apply_single_slash_path(self):
        """Path '/' returns unchanged copy."""
        json_data = {"a": 1}
        diff = {"path": "/", "operation": "modify", "new_value": 2}
        result = DiffUtils.apply(diff, json_data)
        assert result == {"a": 1}

    def test_apply_dict_in_list_parent(self):
        """Navigate into a list, then modify a field on a dict element."""
        json_data = {"items": [{"val": 1}]}
        diff = {"path": "/items/0/val", "operation": "modify", "new_value": 99}
        result = DiffUtils.apply(diff, json_data)
        assert result["items"][0]["val"] == 99


# ---------------------------------------------------------------------------
# DiffUtils.revert tests
# ---------------------------------------------------------------------------


class TestDiffUtilsRevert:
    """Tests for DiffUtils.revert()."""

    def test_revert_dict_modify(self):
        """Restore old value after modify."""
        json_data = {"name": "current"}
        diff = {"path": "/name", "operation": "modify", "old_value": "old"}
        result = DiffUtils.revert(diff, json_data)
        assert result["name"] == "old"

    def test_revert_dict_add(self):
        """Remove key added by modify."""
        json_data = {"name": "added"}
        diff = {"path": "/name", "operation": "modify", "old_value": None}
        result = DiffUtils.revert(diff, json_data)
        assert result["name"] is None

    def test_revert_dict_delete(self):
        """Restore deleted key."""
        json_data = {"keep": True}
        diff = {"path": "/name", "operation": "delete", "old_value": "deleted"}
        result = DiffUtils.revert(diff, json_data)
        assert result["name"] == "deleted"

    def test_revert_array_modify(self):
        """Restore array element after modify."""
        json_data = {"items": [{"x": 99}]}
        diff = {"path": "/items/0/x", "operation": "modify", "old_value": 1}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"][0]["x"] == 1

    def test_revert_array_add(self):
        """Remove element added by modify."""
        json_data = {"items": [{"x": 1}, {"x": 99}]}
        diff = {"path": "/items/1", "operation": "modify", "old_value": None}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == [{"x": 1}, None]

    def test_revert_array_delete(self):
        """Restore deleted array element."""
        json_data = {"items": [{"x": 1}]}
        diff = {"path": "/items/0", "operation": "delete", "old_value": {"x": 1}}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == [{"x": 1}]

    def test_revert_nested(self):
        """Restore nested path."""
        json_data = {"howToRedeem": [{"mode": "a", "title": "current"}]}
        diff = {"path": "/howToRedeem/0/title", "operation": "modify", "old_value": "old"}
        result = DiffUtils.revert(diff, json_data)
        assert result["howToRedeem"][0]["title"] == "old"

    def test_revert_empty_diffs(self):
        """Empty diff returns a deep copy."""
        json_data = {"a": 1}
        result = DiffUtils.revert({}, json_data)
        assert result == {"a": 1}
        assert result is not json_data

    def test_revert_nonexistent_key(self):
        """No-op for key that does not exist."""
        json_data = {"a": 1}
        diff = {"path": "/b", "operation": "modify", "old_value": 2}
        result = DiffUtils.revert(diff, json_data)
        assert result["b"] == 2

    def test_revert_empty_path(self):
        """Empty path returns unchanged copy."""
        json_data = {"a": 1}
        diff = {"path": "", "operation": "modify", "old_value": 2}
        result = DiffUtils.revert(diff, json_data)
        assert result == {"a": 1}

    def test_revert_single_slash(self):
        """Path '/' returns unchanged copy."""
        json_data = {"a": 1}
        diff = {"path": "/", "operation": "modify", "old_value": 2}
        result = DiffUtils.revert(diff, json_data)
        assert result == {"a": 1}

    def test_revert_array_modify_out_of_bounds(self):
        """Restore element appended by out-of-bounds modify."""
        json_data = {"items": [{"x": 1}, {"x": 99}]}
        diff = {"path": "/items/5/x", "operation": "modify", "old_value": None}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"] == [{"x": 1}, {"x": 99}, None]

    def test_revert_dict_in_list_parent(self):
        """Navigate into list, revert field on dict element."""
        json_data = {"items": [{"val": 99}]}
        diff = {"path": "/items/0/val", "operation": "modify", "old_value": 1}
        result = DiffUtils.revert(diff, json_data)
        assert result["items"][0]["val"] == 1
