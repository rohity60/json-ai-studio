"""Diff mutation utilities.

Apply or revert a single diff entry on a JSON dict, in-place.
Used by both single-diff accept and reject endpoints to keep
both working_json and baseline_json in sync.
"""

from __future__ import annotations

from typing import Any


class DiffUtils:
    """Apply or revert a single diff entry on a JSON dict.

    Reuses the path-navigation + operation logic currently duplicated
    across accept_single and reject_single endpoints.
    """

    @staticmethod
    def apply(diff: dict[str, Any], json: dict[str, Any]) -> dict[str, Any]:
        """Apply diff to json in-place. Returns mutated json."""
        path_parts: list[str] = [p for p in diff.get("path", "/").split("/") if p]
        target_key: str | None = path_parts[-1] if path_parts else None
        if target_key:
            current: Any = json
            for part in path_parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    break
                current = current[part]
            else:
                if diff.get("operation") == "delete":
                    current.pop(target_key, None)
                else:
                    current[target_key] = diff.get("new_value")
        return json

    @staticmethod
    def revert(diff: dict[str, Any], json: dict[str, Any]) -> dict[str, Any]:
        """Revert diff on json in-place. Returns mutated json."""
        path_parts: list[str] = [p for p in diff.get("path", "/").split("/") if p]
        target_key: str | None = path_parts[-1] if path_parts else None
        if target_key:
            current: Any = json
            for part in path_parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    break
                current = current[part]
            else:
                op: str = diff.get("operation", "")
                if op == "add":
                    current.pop(target_key, None)
                elif op == "modify" and "old_value" in diff:
                    current[target_key] = diff["old_value"]
                elif op == "delete" and "old_value" in diff:
                    current[target_key] = diff["old_value"]
        return json
