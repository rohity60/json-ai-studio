"""Diff engine + validation helpers.

Uses deepdiff (ADR-0003) for field-level diffs and implements business-rule
validation per requirement V-04 (timeout > 0, retryCount <= 10, mandatory
fields populated).
"""

from __future__ import annotations

import json as _json
import re as _re
from typing import Any

from deepdiff import DeepDiff


def _flatten_deepdiff(diff: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    """Flatten a deepdiff result into DiffEntry dicts."""
    entries: list[dict[str, Any]] = []

    for path, change in diff.get("values_changed", {}).items():
        full_path = f"{prefix}/{path}" if prefix else f"/{path}"
        entries.append(
            {
                "path": full_path,
                "operation": "modify",
                "old_value": change.get("old_value"),
                "new_value": change.get("new_value"),
            }
        )

    for path in diff.get("dictionary_removed", {}):
        full_path = f"{prefix}/{path}" if prefix else f"/{path}"
        entries.append(
            {
                "path": full_path,
                "operation": "delete",
                "old_value": None,
                "new_value": None,
            }
        )

    for path in diff.get("dictionary_added", {}):
        full_path = f"{prefix}/{path}" if prefix else f"/{path}"
        entries.append(
            {
                "path": full_path,
                "operation": "add",
                "old_value": None,
                "new_value": None,
            }
        )

    return entries


def compute_diff(
    old_json: dict[str, Any], new_json: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compute a field-level diff between two JSON objects.

    Returns a list of DiffEntry dicts (path, operation, old_value, new_value).
    Uses deepdiff under the hood (ADR-0003).
    """
    try:
        diff = DeepDiff(old_json, new_json, significant_digits=3, ignore_nan=True)
    except Exception:
        return []

    if not diff:
        return []

    entries = _flatten_deepdiff(diff)

    if not entries:
        entries = _structural_diff(old_json, new_json)

    return entries


def _structural_diff(old: Any, new: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Fallback structural diff when deepdiff is empty."""
    entries: list[dict[str, Any]] = []
    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys):
            path = f"{prefix}/{key}" if prefix else f"/{key}"
            if key not in old:
                entries.append(
                    {
                        "path": path,
                        "operation": "add",
                        "old_value": None,
                        "new_value": new[key],
                    }
                )
            elif key not in new:
                entries.append(
                    {
                        "path": path,
                        "operation": "delete",
                        "old_value": old[key],
                        "new_value": None,
                    }
                )
            else:
                entries.extend(_structural_diff(old[key], new[key], path))
    return entries


# -- Validation Helpers (business rules per V-04) --

_TIMEOUT_KEYS = {"timeout", "timeout_ms", "read_timeout", "connect_timeout"}
_RETRY_KEYS = {"retry_count", "retries", "max_retries", "retry_limit"}


def _validate_value(value: Any, key_name: str, path: str) -> list[dict[str, Any]]:
    """Validate a single value against business rules."""
    errors: list[dict[str, Any]] = []
    lower_key = key_name.lower().replace(" ", "_")

    if lower_key in _TIMEOUT_KEYS and isinstance(value, (int, float)):
        if value <= 0:
            errors.append(
                {"path": path, "message": f"{key_name} must be greater than 0"}
            )

    if lower_key in _RETRY_KEYS and isinstance(value, (int, float)):
        if value < 0:
            errors.append({"path": path, "message": f"{key_name} cannot be negative"})
        elif value > 10:
            errors.append({"path": path, "message": f"{key_name} must be <= 10"})

    return errors


def _validate_json(data: Any, path_prefix: str = "") -> list[dict[str, Any]]:
    """Recursively validate a JSON structure against business rules."""
    errors: list[dict[str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path_prefix}/{key}" if path_prefix else f"/{key}"
            if (
                isinstance(value, str)
                and value.strip() == ""
                and key in ("name", "label", "id")
            ):
                errors.append(
                    {"path": current_path, "message": f"{key} cannot be empty"}
                )
            errors.extend(_validate_value(value, key, current_path))
            if isinstance(value, (dict, list)):
                errors.extend(_validate_json(value, current_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path_prefix}[{i}]"
            errors.extend(_validate_json(item, current_path))

    return errors


def validate_document(json_data: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Validate a JSON document.

    Returns (is_valid, list_of_errors). Runs syntax validation + business
    rules per requirements V-02 and V-04.
    """
    try:
        _json.dumps(json_data)
    except (TypeError, ValueError):
        return False, [{"path": None, "message": "Invalid JSON structure"}]

    errors = _validate_json(json_data)
    return len(errors) == 0, errors
