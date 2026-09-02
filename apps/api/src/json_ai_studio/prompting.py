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

from .settings import get_settings

# The verbatim-inline threshold now lives in Settings
# (llm_max_inline_chars); above it, build_system_prompt sends a typed
# skeleton instead of the full document.

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
6. For "add", the new key NOT existing in the CURRENT WORKING JSON is expected — never refuse an add because the key is missing. If the user does not say where to put the new key, add it at the TOP LEVEL of the document (path "/<key>"). Strip units or currency words from values ("10 rs" -> 10). Only return empty diffs for an add when the user names a container that does not exist.
7. If a modify or delete request cannot be applied (target not found, ambiguous, or unrelated to this JSON), return {"diffs": [], "explanation": "..."} — say why, list what actually exists, and suggest the closest match.
8. When duplicating an object, add the copy at the same level as the source with the same keys and values, unless the user specifies new ones.
9. Multiple requested changes = multiple entries in the "diffs" array of the SAME single object.
10. If the user's message is ITSELF a whole new JSON document (a full configuration pasted as the message, not an instruction) that they seem to want to work on, do NOT adopt, replace, or merge it into the CURRENT WORKING JSON — return {"diffs": [], "explanation": "It looks like you pasted a full JSON document. To work on it, load it with the Upload feature; then describe the changes you want here."}. This does NOT apply when JSON appears as an EXAMPLE inside an instruction (e.g. "add an entry like {...}", "make it match this shape: {...}") — there, use the provided JSON to build the correct diffs against the CURRENT WORKING JSON.

EXAMPLES (illustrative only — real answers must use paths, values, and indices from the CURRENT WORKING JSON above, never from these examples):

User: "Set timeout to 60 for the api service."
JSON: {"services": {"api": {"timeout": 30}}}
Response: {"diffs": [{"path": "/services/api/timeout", "operation": "modify", "old_value": 30, "new_value": 60}], "explanation": "Changed api service timeout from 30 to 60."}

User: "Add retryCount of 5 to the default service."
JSON: {"services": {"default": {}}}
Response: {"diffs": [{"path": "/services/default/retryCount", "operation": "add", "old_value": null, "new_value": 5}], "explanation": "Added retryCount 5 to the default service."}

User: "add price 10 rs" (no location given — new keys go to the top level; the key not existing yet is normal for an add)
JSON: {"services": {"api": {"timeout": 30}}}
Response: {"diffs": [{"path": "/price", "operation": "add", "old_value": null, "new_value": 10}], "explanation": "Added price 10 at the top level."}

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

DOMAIN AWARENESS:
- Identify the business/technical domain from the key names, value formats, and
  enum values actually present in the document (e.g. payment webhooks, ecommerce
  orders, CI/CD pipelines, IAM policies, telemetry, Kubernetes manifests,
  feature flags, healthcare records).
- Explain the key concepts of that domain, but ONLY those tied to keys present
  in this payload: entity lifecycles and state machines (e.g. authorized ->
  captured -> refunded), naming conventions (entity.action event names, ISO
  codes, IDs with type prefixes), unit conventions (amounts in minor currency
  units, timestamps in epoch seconds/ms), and what each enum value implies in
  practice.
- Where a field's value looks like a placeholder or violates the domain's norms
  (test URLs, localhost endpoints, weak secrets, impossible amounts), say so.
- Treat secret-like fields (secret, token, api_key, password, credential) with
  care: assess their strength and flag weak/placeholder values as a security
  issue, but NEVER repeat the value itself in your explanation.
- If the domain is unclear, say so and describe the most likely candidates
  instead of guessing confidently.

Respond with markdown sections in this exact order:

## Summary
One paragraph describing what this JSON represents at a high level (e.g., "This JSON represents an ecommerce order with customer details, shipping information, line items, and payment data.").

## What this JSON represents
2-3 sentences about the domain, purpose, and likely source of this JSON (API response, config file, log, etc.).

## Domain Concepts
Explain the domain-specific concepts behind the fields present in this payload:
what each significant field/enum means in this domain, relevant lifecycles or
flows, and conventions a developer must know to work with this data correctly.

## Main Objects
Bullet list of top-level keys and what each one represents.

## Relationships
Describe how the main objects relate to each other (e.g., "customer.id matches the customerId field in orders").

## Important Fields
List key fields with their types and typical values. Note any nested structures.

## Interesting Observations
Highlight notable patterns: array lengths, computed totals, missing optional fields,
enum values, unusual nesting, or domain-specific insights (e.g. lifecycle stages
covered vs. missing).

## Potential Issues
Flag missing required fields, suspicious values, empty arrays, or potential data
quality concerns — including domain-norm violations and weak secret-like values
(without repeating them).

## Suggested Next Questions
3-5 follow-up questions a developer might ask (e.g., "What does the customer object contain?", "Show payment flow", "Find nullable fields").

Do NOT use markdown code fences. Output raw markdown only.
"""


# Skeleton bounds for the too-large-to-inline path. Keep the skeleton itself
# small while still carrying nested key names and representative values.
_SKELETON_MAX_DEPTH = 8
_SKELETON_STR_CAP = 80  # truncate long string values to this many chars
_SKELETON_DICT_KEY_CAP = 300  # cap keys shown per object


def build_skeleton(
    data: Any,
    depth: int = 0,
    *,
    max_depth: int = _SKELETON_MAX_DEPTH,
    str_cap: int = _SKELETON_STR_CAP,
    key_cap: int = _SKELETON_DICT_KEY_CAP,
) -> Any:
    """Compact, size-bounded structural skeleton of a JSON value.

    Unlike a bare key list, this preserves the full nested key structure
    AND representative values so the model can reason about a document too
    large to inline verbatim:
      - dict  -> every key mapped to its child skeleton (capped at key_cap).
      - list  -> the first element's skeleton plus a "…+N more items" marker,
                 so array length is conveyed without dumping every element.
      - str   -> the value, truncated to str_cap chars.
      - number/bool/null -> kept as-is (small, high-signal).
    """
    if isinstance(data, dict):
        if depth >= max_depth:
            return {"…": f"<{len(data)} keys, depth capped>"}
        out: dict[str, Any] = {}
        for i, (key, value) in enumerate(data.items()):
            if i >= key_cap:
                out["…"] = f"+{len(data) - key_cap} more keys"
                break
            out[str(key)] = build_skeleton(
                value, depth + 1, max_depth=max_depth, str_cap=str_cap, key_cap=key_cap
            )
        return out
    if isinstance(data, list):
        if not data:
            return []
        head = build_skeleton(
            data[0], depth + 1, max_depth=max_depth, str_cap=str_cap, key_cap=key_cap
        )
        if len(data) == 1:
            return [head]
        return [head, f"…+{len(data) - 1} more items"]
    if isinstance(data, str):
        return data if len(data) <= str_cap else data[:str_cap] + "…"
    return data


def build_system_prompt(working_json: dict[str, Any]) -> str:
    """Build the system prompt with the working JSON inlined."""
    max_inline = get_settings().llm_max_inline_chars
    pretty = json.dumps(working_json, indent=2, ensure_ascii=False, default=str)
    if len(pretty) <= max_inline:
        context = f"CURRENT WORKING JSON:\n{pretty}"
    else:
        compact = json.dumps(
            working_json, separators=(",", ":"), ensure_ascii=False, default=str
        )
        if len(compact) <= max_inline:
            context = f"CURRENT WORKING JSON:\n{compact}"
        else:
            skeleton = json.dumps(
                build_skeleton(working_json),
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            context = (
                "The working JSON is too large to inline in full. Below is a "
                "STRUCTURAL SKELETON: the complete nested key structure with "
                "SAMPLE values — long strings are truncated with an ellipsis, "
                'and arrays show only their first element plus a "…+N more '
                'items" marker (so N+1 is the array length).\n'
                f"{skeleton}\n"
                "You may rely on the keys and the sample values shown. For "
                "large arrays you can see only the first element's shape: when "
                "a request targets a specific element by a value you cannot "
                "see, or asks to rewrite values across every element, return "
                '{"diffs": [], "explanation": "..."} and ask the user to '
                "narrow it to a specific index or field."
            )
    return _TEMPLATE.replace("__CONTEXT__", context)
