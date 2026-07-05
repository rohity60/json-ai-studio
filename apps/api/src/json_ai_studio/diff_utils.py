"""Diff mutation utilities.

Apply or revert a single diff entry on a JSON dict/list, in-place.
Used by both single-diff accept and reject endpoints to keep
both working_json and baseline_json in sync.

Path navigation handles both dicts and lists. Numeric path parts
index into arrays (e.g. "/items/0/name" -> items[0]["name"]).
"""

from __future__ import annotations

from typing import Any


class DiffUtils:
    """Apply or revert a single diff entry on a JSON dict/list.

    Reuses the path-navigation + operation logic currently duplicated
    across accept_single and reject_single endpoints.
    """

    @staticmethod
    def _navigate(obj: Any, parts: list[str]) -> tuple[Any, str | None]:
        """Navigate to parent of target, return (parent, target_key).

        Numeric path parts index into lists. String parts access dicts.
        """
        current = obj
        for part in parts[:-1]:
            if part.isdigit():
                idx = int(part)
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return current, parts[-1]
            else:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list):
                    return current, parts[-1]
                else:
                    current[part] = {}
                    current = current[part]
        return current, parts[-1]

    @staticmethod
    def apply(diff: dict[str, Any], json: dict[str, Any]) -> dict[str, Any]:
        """Apply diff to json in-place. Returns mutated json."""
        import copy

        result = copy.deepcopy(json)
        path_parts: list[str] = [p for p in diff.get("path", "/").split("/") if p]
        if not path_parts:
            return result

        parent, target_key = DiffUtils._navigate(result, path_parts)
        if target_key is None:
            return result

        op = diff.get("operation", "")
        if op == "delete":
            if isinstance(parent, dict):
                parent.pop(target_key, None)
            elif isinstance(parent, list):
                try:
                    parent.pop(int(target_key))
                except (ValueError, IndexError):
                    pass
        else:
            if isinstance(parent, dict):
                parent[target_key] = diff.get("new_value")
            elif isinstance(parent, list):
                try:
                    idx = int(target_key)
                    if idx < len(parent):
                        parent[idx] = diff.get("new_value")
                    else:
                        parent.append(diff.get("new_value"))
                except (ValueError, IndexError):
                    parent.append({target_key: diff.get("new_value")})
        return result

    @staticmethod
    def revert(diff: dict[str, Any], json: dict[str, Any]) -> dict[str, Any]:
        """Revert diff on json in-place. Returns mutated json."""
        import copy

        result = copy.deepcopy(json)
        path_parts: list[str] = [p for p in diff.get("path", "/").split("/") if p]
        if not path_parts:
            return result

        parent, target_key = DiffUtils._navigate(result, path_parts)
        if target_key is None:
            return result

        op = diff.get("operation", "")
        if op == "add":
            if isinstance(parent, dict):
                parent.pop(target_key, None)
            elif isinstance(parent, list):
                try:
                    parent.pop(int(target_key))
                except (ValueError, IndexError):
                    pass
        elif op == "modify" and "old_value" in diff:
            if isinstance(parent, dict):
                parent[target_key] = diff["old_value"]
            elif isinstance(parent, list):
                try:
                    idx = int(target_key)
                    if idx < len(parent):
                        parent[idx] = diff["old_value"]
                    else:
                        parent.append(diff["old_value"])
                except (ValueError, IndexError):
                    parent.append(diff["old_value"])
        elif op == "delete" and "old_value" in diff:
            if isinstance(parent, dict):
                parent[target_key] = diff["old_value"]
            elif isinstance(parent, list):
                try:
                    idx = int(target_key)
                    if idx < len(parent):
                        parent[idx] = diff["old_value"]
                    else:
                        parent.append(diff["old_value"])
                except (ValueError, IndexError):
                    parent.append(diff["old_value"])
        return result

    @staticmethod
    def apply_all(diffs: list[dict[str, Any]], json: dict[str, Any]) -> dict[str, Any]:
        """Apply a list of diffs to json. Returns new copy."""
        import copy

        result = copy.deepcopy(json)
        for diff in diffs:
            path_parts: list[str] = [p for p in diff.get("path", "/").split("/") if p]
            if not path_parts:
                continue
            parent, target_key = DiffUtils._navigate(result, path_parts)
            if target_key is None:
                continue
            op = diff.get("operation", "")
            if op == "delete":
                if isinstance(parent, dict):
                    parent.pop(target_key, None)
                elif isinstance(parent, list):
                    try:
                        parent.pop(int(target_key))
                    except (ValueError, IndexError):
                        pass
            else:
                if isinstance(parent, dict):
                    parent[target_key] = diff.get("new_value")
                elif isinstance(parent, list):
                    try:
                        idx = int(target_key)
                        if idx < len(parent):
                            parent[idx] = diff.get("new_value")
                        else:
                            parent.append(diff.get("new_value"))
                    except (ValueError, IndexError):
                        parent.append({target_key: diff.get("new_value")})
        return result
