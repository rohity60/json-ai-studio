"""System prompt construction for the JSON-editing LLM call.

Embeds the full current working JSON so the model can produce exact
old_value / index / path references (ADR-0005). Falls back to a schema
summary only when the document is too large to inline, and in that
case instructs the model not to guess values it cannot see.

The output contract is a single JSON object:
    {"diffs": [DiffEntry, ...], "explanation": "..."}
which removes the old contradiction between "output only a JSON array"
and "explain in plain text when the request cannot be applied".
"""

from __future__ import annotations

import json
from typing import Any

# Above this many serialized characters we stop inlining the document.
# Large payloads previously froze local Ollama backends for 5-60s.
MAX_INLINE_CHARS = 60_000

_TEMPLATE = """\
You are a JSON configuration editor. The user describes a change in natural \
language; you respond with a machine-readable change proposal.

__CONTEXT__

OUTPUT FORMAT — respond with EXACTLY ONE JSON object and nothing else. No \
markdown, no code fences, no text before or after the object:
{"diffs": [{"path": "<JSON Pointer>", "operation": "add" | "modify" | "delete", "old_value": <value>, "new_value": <value>}], "explanation": "<one short sentence for the user>"}

RULES:
1. "path" is a JSON Pointer: segments joined by "/". Escape "/" inside a key as "~1" and "~" as "~0".
2. "old_value" must be copied EXACTLY from the CURRENT WORKING JSON above. Use null for "add".
3. For "delete", set "old_value" to the exact value being removed and "new_value" to null.
4. Array indices are zero-based and must match the CURRENT WORKING JSON above. To append, use an index equal to the array's current length.
5. To change or remove an array element identified by a field value (e.g. where mode is "c"), find that element's index in the CURRENT WORKING JSON above and use it in the path.
6. If the request cannot be applied (target not found, ambiguous, or unrelated to this JSON), return {"diffs": [], "explanation": "..."} — say why, list what actually exists, and suggest the closest match.
7. When duplicating an object, add the copy at the same level as the source with the same keys and values, unless the user specifies new ones.
8. Multiple requested changes = multiple entries in the "diffs" array of the SAME single object.

EXAMPLES (illustrative only — real answers must use paths, values, and indices from the CURRENT WORKING JSON above, never from these examples):

User: "Set timeout to 60 for the api service."
JSON: {"services": {"api": {"timeout": 30}}}
Response: {"diffs": [{"path": "/services/api/timeout", "operation": "modify", "old_value": 30, "new_value": 60}], "explanation": "Changed api service timeout from 30 to 60."}

User: "Add retryCount of 5 to the default service."
JSON: {"services": {"default": {}}}
Response: {"diffs": [{"path": "/services/default/retryCount", "operation": "add", "old_value": null, "new_value": 5}], "explanation": "Added retryCount 5 to the default service."}

User: "Add a step with mode 'd' titled 'Step 3'." (the array currently has 2 elements, indices 0 and 1)
JSON: {"howToRedeem": [{"mode": "a", "title": "Step 1"}, {"mode": "c", "title": "Step 2"}]}
Response: {"diffs": [{"path": "/howToRedeem/2", "operation": "add", "old_value": null, "new_value": {"mode": "d", "title": "Step 3"}}], "explanation": "Appended a new step at the end of howToRedeem."}

User: "Remove the step with mode 'c'."
JSON: {"howToRedeem": [{"mode": "a", "title": "Step 1"}, {"mode": "c", "title": "Step 2"}]}
Response: {"diffs": [{"path": "/howToRedeem/1", "operation": "delete", "old_value": {"mode": "c", "title": "Step 2"}, "new_value": null}], "explanation": "Removed the step with mode 'c' (index 1)."}

User: "Update the title where mode is 'b'." (no element has mode 'b')
JSON: {"howToRedeem": [{"mode": "a", "title": "Step 1"}, {"mode": "c", "title": "Step 2"}]}
Response: {"diffs": [], "explanation": "No element in howToRedeem has mode 'b'; existing modes are 'a' (index 0) and 'c' (index 1). Did you mean mode 'c'?"}

Now respond to the user's message using ONLY the CURRENT WORKING JSON above.
"""

EXPLAIN_TEMPLATE = """\
You are a JSON explanation engine. The user has uploaded a JSON document and wants
to understand what it represents, its structure, and important details.

Explain this JSON as if helping a developer understand it for the first time.

Respond with markdown sections in this exact order:

## Summary
One paragraph describing what this JSON represents at a high level (e.g., "This JSON represents an ecommerce order with customer details, shipping information, line items, and payment data.").

## What this JSON represents
2-3 sentences about the domain, purpose, and likely source of this JSON (API response, config file, log, etc.).

## Main Objects
Bullet list of top-level keys and what each one represents.

## Relationships
Describe how the main objects relate to each other (e.g., "customer.id matches the customerId field in orders").

## Important Fields
List key fields with their types and typical values. Note any nested structures.

## Interesting Observations
Highlight notable patterns: array lengths, computed totals, missing optional fields,
enum values, unusual nesting, or domain-specific insights.

## Potential Issues
Flag missing required fields, suspicious values, empty arrays, or potential data quality concerns.

## Suggested Next Questions
3-5 follow-up questions a developer might ask (e.g., "What does the customer object contain?", "Show payment flow", "Find nullable fields").

Do NOT use markdown code fences. Output raw markdown only.
"""


def compute_schema_summary(data: Any, prefix: str = "") -> dict[str, Any]:
    """Summarize structure: keys, nesting depth, array lengths by path."""
    top_keys: list[str] = []
    max_depth = 0
    array_lengths: dict[str, int] = {}

    if isinstance(data, dict):
        top_keys = list(data.keys())
        for key, value in data.items():
            child = compute_schema_summary(value, f"{prefix}/{key}")
            max_depth = max(max_depth, child["nested_depth"] + 1)
            array_lengths.update(child["array_lengths"])
    elif isinstance(data, list):
        array_lengths[prefix or "/"] = len(data)
        for i, item in enumerate(data[:1]):  # sample first element's shape
            child = compute_schema_summary(item, f"{prefix}/{i}")
            max_depth = max(max_depth, child["nested_depth"] + 1)
            array_lengths.update(child["array_lengths"])

    return {
        "top_level_keys": top_keys,
        "nested_depth": max_depth,
        "array_lengths": array_lengths,
    }


def build_system_prompt(working_json: dict[str, Any]) -> str:
    """Build the system prompt with the working JSON inlined."""
    pretty = json.dumps(working_json, indent=2, ensure_ascii=False, default=str)
    if len(pretty) <= MAX_INLINE_CHARS:
        context = f"CURRENT WORKING JSON:\n{pretty}"
    else:
        compact = json.dumps(
            working_json, separators=(",", ":"), ensure_ascii=False, default=str
        )
        if len(compact) <= MAX_INLINE_CHARS:
            context = f"CURRENT WORKING JSON:\n{compact}"
        else:
            summary = json.dumps(compute_schema_summary(working_json), indent=2)
            context = (
                "The working JSON is too large to show in full. "
                "STRUCTURE SUMMARY (keys, depth, array lengths by path):\n"
                f"{summary}\n"
                "You cannot see the actual values. Only propose diffs whose "
                "paths you can verify from this summary; when the request "
                "depends on values you cannot see, return "
                '{"diffs": [], "explanation": "..."} asking the user to '
                "narrow the request."
            )
    return _TEMPLATE.replace("__CONTEXT__", context)
