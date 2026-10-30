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

from .format_hints import format_notes_block
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
Optionally add a "question" to the SAME object when you must ask the user (rule 12):
{"diffs": [], "question": {"text": "<one short question>", "options": ["<option 1>", "<option 2>"]}, "explanation": "..."}
Optionally add a "bulk" list to the SAME object for changes that hit many elements (see BULK EDITS):
{"diffs": [], "bulk": [{"path": "<JSON Pointer with * wildcards>", "where": {<conditions>}, "operation": "modify" | "add" | "delete", "new_value": <value>}], "explanation": "..."}

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
11. FORMAT CORRECTNESS — on EVERY request, besides what the user asked, also propose fixes for values or structure in the CURRENT WORKING JSON that are wrong for the document's format: anything that breaks the FORMAT NOTES (when given), or a well-known rule of the format the document evidently follows (a value the target system rejects, a key in the wrong place, placeholder syntax the system does not support, a wrong port or protocol). Make each fix its own diff, and in "explanation" list EACH fix and why — the rule it breaks — in a sentence or two per fix ("explanation" may be longer than one sentence for this). EXCEPTION: when the user explicitly asks for a specific key or value, apply exactly that even if it breaks the format, and warn in "explanation" why it is likely wrong — never silently override the user. Only fix what you are confident about; never invent model names, ports, commands or IDs that neither FORMAT NOTES nor the user gave — if the correct value is unknown, leave it and say what is wrong. If nothing is wrong, propose no extra fixes.
12. QUESTIONS — ask only when the request has more than one reasonable reading you cannot resolve from the JSON (or with tools, when you have them), or a value you need is missing. Return "question" with "text" and 2-4 short "options" covering the readings (e.g. {"text": "Apply 'abc' to which records?", "options": ["Only chapter 1 (47 records)", "All 701 records"]}), no diffs for the ambiguous part, and say in "explanation" why you are asking. Never ask instead of looking something up, never ask about something the user already said, and never ask when one reading is clearly intended.
13. ANALYSIS — when the user asks you to analyze, explain, trace, find or check something before (or instead of) editing, you may return no diffs and a longer "explanation" (up to ~8 sentences) that cites the exact JSON paths you relied on. If they asked for a proposal "before editing", describe the change and its paths in "explanation" and do not emit diffs yet.

BULK EDITS — use "bulk" instead of listing diffs one by one whenever a change applies to more than 5 elements, or to elements you cannot see (structural skeleton). The server expands each bulk op against the FULL document, so you do NOT need to see or copy the matching values.
B1. "path" is a JSON Pointer where "*" matches every array element (or object key) at that level, e.g. "/records/*/sectionId".
B2. "where" (optional) filters the element matched by the LAST "*". Keys are field names inside that element (or relative pointers like "meta/id"); "$index" is its zero-based array index; "$value" is the targeted value itself. A plain value means equality (strings compare case-insensitively); an object uses operators: eq, ne, in, nin, gt, gte, lt, lte, contains (substring), exists.
B3. "operation": "modify" sets new_value; "add" sets it only where the key is missing; "delete" removes the matched node (e.g. path "/files/*" deletes whole elements).
B4. Prefer conditions on a real field the user names (e.g. "slokNumber" 1 to 100 → {"slokNumber": {"gte": 1, "lte": 100}}). Positional words ("first 20", "first 100 records", "top 5", "last 10") ALWAYS mean array position → {"$index": {"lt": 20}}, never a range on a numeric field (fields like a verse/step number often restart per group — see ARRAY FIELD STATS). Do not put the same change in both "diffs" and "bulk".
B5. To copy a value from ANOTHER FIELD of the same element, set "new_value" to {"$from": "<field name or relative pointer>"} — the server copies each element's own value. NEVER write a placeholder or description (like "same as creationDate") as new_value.

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

User: "Add a test script using vitest." (rule 11: fix format problems too)
JSON: {"name": "My App", "version": "1.0", "scripts": {"start": "node index.js"}}
Response: {"diffs": [{"path": "/scripts/test", "operation": "add", "old_value": null, "new_value": "vitest"}, {"path": "/name", "operation": "modify", "old_value": "My App", "new_value": "my-app"}, {"path": "/version", "operation": "modify", "old_value": "1.0", "new_value": "1.0.0"}], "explanation": "Added a vitest test script. Also fixed 2 issues: name 'My App' → 'my-app' because npm package names must be lowercase with no spaces; version '1.0' → '1.0.0' because npm requires full semver (major.minor.patch)."}

User: "Set the name to My App." (explicit request — apply it, but warn)
JSON: {"name": "my-app", "version": "1.0.0"}
Response: {"diffs": [{"path": "/name", "operation": "modify", "old_value": "my-app", "new_value": "My App"}], "explanation": "Set name to 'My App' as requested. Note: npm rejects package names with uppercase letters or spaces, so publishing or installing this package will fail."}

User: "Set status to DONE for every record with chapter 2." (large array)
JSON: {"records": [{"chapter": 1, "status": "OPEN"}, "…+700 more items"]}
Response: {"diffs": [], "bulk": [{"path": "/records/*/status", "where": {"chapter": 2}, "operation": "modify", "new_value": "DONE"}], "explanation": "Set status to DONE for every record in chapter 2."}

User: "Make every item's updatedAt equal to its createdAt."
JSON: {"items": [{"createdAt": "2024-01-01", "updatedAt": "2024-05-02"}, "…+499 more items"]}
Response: {"diffs": [], "bulk": [{"path": "/items/*/updatedAt", "operation": "modify", "new_value": {"$from": "createdAt"}}], "explanation": "Set each item's updatedAt to its own createdAt."}

User: "Delete every file whose title mentions draft 2027."
JSON: {"files": [{"title": "Draft 2027 - Round 1"}, {"title": "Roster 2026"}, {"title": "Draft 2027 - Round 2"}]}
Response: {"diffs": [], "bulk": [{"path": "/files/*", "where": {"title": {"contains": "draft 2027"}}, "operation": "delete"}], "explanation": "Deleted the files whose title mentions Draft 2027."}

__HISTORY__Now respond to the user's message using ONLY the CURRENT WORKING JSON above.
"""

# Appended only when prior turns are replayed. Earlier assistant messages
# are the model's own past responses, each diff annotated with "status"
# reflecting what the user did with it.
_HISTORY_RULES = """\
CONVERSATION HISTORY RULES — earlier messages in this conversation are prior \
turns. Your earlier responses are shown in the output format above, with a \
"status" on every diff:
- "accepted": the user kept it. It is ALREADY in the CURRENT WORKING JSON.
- "pending": shown to the user, not yet accepted or rejected. It is ALREADY in the CURRENT WORKING JSON.
- "rejected": the user declined it. It was reverted and is NOT in the CURRENT WORKING JSON.
- "failed": it did not match the JSON and was never applied.
H1. History tells you INTENT only. Every path, index, and old_value MUST come from the CURRENT WORKING JSON — paths and indices in history may be stale.
H2. Never re-propose an "accepted" or "pending" change; it is already applied.
H3. Do not repeat a "rejected" change unless the user explicitly asks for it again.
H4. If the user repeats a "failed" request, re-derive the paths from the CURRENT WORKING JSON.
H5. For follow-ups like "do the same for all of them", "the rest", "for every such element": generalise the most recent accepted/pending change to EVERY matching location in the CURRENT WORKING JSON. Skip only the exact paths already changed (accepted/pending) and the paths whose equivalent change was rejected — other matching values inside the same element still count.
H5a. Generalise the SAME change at the SAME granularity: if the earlier diff changed one leaf value (old_value -> new_value), emit one leaf diff per matching location where the CURRENT value equals that old_value (or that the user names). Never replace a whole array or object, and never touch values that do not match, unless the user explicitly asks for it.
H6. Resolve references like "it", "that", "the second one", "undo that" against the previous turns.

HISTORY EXAMPLE (illustrative only):
Earlier user: "Set retryCount to 3 for the payments service."
Earlier response: {"diffs": [{"path": "/services/payments/retryCount", "operation": "modify", "old_value": 5, "new_value": 3, "status": "accepted"}], "explanation": "Set payments retryCount to 3."}
User: "Do it for all such services."
JSON: {"services": {"payments": {"retryCount": 3}, "orders": {"retryCount": 5}, "search": {"retryCount": 1}}}
Response: {"diffs": [{"path": "/services/orders/retryCount", "operation": "modify", "old_value": 5, "new_value": 3}, {"path": "/services/search/retryCount", "operation": "modify", "old_value": 1, "new_value": 3}], "explanation": "Set retryCount to 3 for orders and search; payments already had it."}

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


_SKELETON_MAX_TYPES = 12  # $type variants shown per array


def short_type(value: Any) -> str:
    """'UAssetAPI.Kismet.Bytecode.Expressions.EX_Return, UAssetAPI' -> 'EX_Return'."""
    return str(value).split(",")[0].rsplit(".", 1)[-1]


def build_skeleton(
    data: Any,
    depth: int = 0,
    *,
    max_depth: int = _SKELETON_MAX_DEPTH,
    str_cap: int = _SKELETON_STR_CAP,
    key_cap: int = _SKELETON_DICT_KEY_CAP,
) -> Any:
    """Compact, size-bounded structural skeleton of a JSON value.

    Shows EVERY key that occurs anywhere, with representative values:
      - dict  -> every key mapped to its child skeleton (capped at key_cap).
      - list  -> ONE sample element whose keys are the UNION over all
                 elements (keys only some elements have are listed under
                 "…keys in only some items"), plus a "…+N more items" marker.
                 Arrays whose elements carry "$type" (e.g. UAssetAPI) show one
                 merged sample per $type plus counts — the first element alone
                 hid whole sections (no ScriptBytecode when Exports[0] was a
                 ClassExport).
      - str   -> the value, truncated to str_cap chars.
      - number/bool/null -> kept as-is (small, high-signal).
    Nested arrays are merged across their parents (counts say so).
    """
    caps = (max_depth, str_cap, key_cap)
    return _skel_values([data], depth, caps)


def _skel_values(vals: list[Any], depth: int, caps: tuple[int, int, int]) -> Any:
    """Skeleton for sibling values that sit at the same position."""
    max_depth, str_cap, key_cap = caps
    dicts = [v for v in vals if isinstance(v, dict)]
    if dicts and len(dicts) == len(vals):
        if depth >= max_depth:
            return {"…": f"<{len(dicts[0])} keys, depth capped>"}
        children: dict[str, list[Any]] = {}
        for obj in dicts:
            for key, value in obj.items():
                children.setdefault(str(key), []).append(value)
        out: dict[str, Any] = {}
        partial: list[str] = []
        for i, (key, values) in enumerate(children.items()):
            if i >= key_cap:
                out["…"] = f"+{len(children) - key_cap} more keys"
                break
            out[key] = _skel_values(values, depth + 1, caps)
            if len(values) < len(dicts):
                partial.append(f"{key} ({len(values)}/{len(dicts)})")
        if partial:
            out["…keys in only some items"] = ", ".join(partial)
        return out
    lists = [v for v in vals if isinstance(v, list)]
    if lists and len(lists) == len(vals):
        return _skel_list([x for lst in lists for x in lst], len(lists), depth, caps)
    first = vals[0]
    if isinstance(first, (dict, list)):  # mixed shapes: fall back to a sample
        return _skel_values([first], depth, caps)
    if isinstance(first, str):
        return first if len(first) <= str_cap else first[:str_cap] + "…"
    return first


def _skel_list(
    items: list[Any], n_arrays: int, depth: int, caps: tuple[int, int, int]
) -> Any:
    if not items:
        return []
    total = len(items)
    scope = f" across {n_arrays} arrays" if n_arrays > 1 else ""
    if all(isinstance(x, dict) for x in items) and any("$type" in x for x in items):
        groups: dict[str, list[Any]] = {}
        for obj in items:
            groups.setdefault(str(obj.get("$type", "<no $type>")), []).append(obj)
        out = [
            _skel_values(group, depth + 1, caps)
            for group in list(groups.values())[:_SKELETON_MAX_TYPES]
        ]
        counts = ", ".join(f"{short_type(t)}×{len(g)}" for t, g in groups.items())
        out.append(f"…{total} items{scope} by $type: {counts}")
        return out
    head = _skel_values(items, depth + 1, caps)
    if total == 1:
        return [head]
    if n_arrays > 1:
        return [head, f"…{total} items{scope}"]
    return [head, f"…+{total - 1} more items"]


_STATS_MAX_ARRAYS = 20
_STATS_MAX_FIELDS = 30
_STATS_TOP_VALUES = 5
_STATS_MAX_DISTINCT_LISTED = 25


def _scalar_key(value: Any) -> Any:
    return (
        value if isinstance(value, (str, int, float, bool)) or value is None else None
    )


def build_array_stats(data: Any) -> list[str]:
    """Per-field value statistics for arrays of objects, skeleton mode only.

    The skeleton shows one sample element per array, so the model can't tell
    whether a field is a unique id, a per-group counter (e.g. slokNumber
    restarting per chapter) or a low-cardinality category. These lines give
    distinct counts, numeric ranges and top values so bulk "where" clauses
    target the right field. Paths use the bulk-edit "*" syntax.
    """
    lines: list[str] = []

    def visit(node: Any, path: str, depth: int) -> None:
        if len(lines) >= _STATS_MAX_ARRAYS or depth > _SKELETON_MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key, child in list(node.items())[:_SKELETON_DICT_KEY_CAP]:
                esc = str(key).replace("~", "~0").replace("/", "~1")
                visit(child, f"{path}/{esc}", depth + 1)
        elif isinstance(node, list) and len(node) > 1:
            objs = [x for x in node if isinstance(x, dict)]
            if len(objs) == len(node):
                fields: list[str] = []
                keys: dict[str, None] = {}
                for o in objs:
                    keys.update(dict.fromkeys(o))
                for key in list(keys)[:_STATS_MAX_FIELDS]:
                    vals = [o[key] for o in objs if key in o]
                    if key == "$type":
                        vals = [short_type(v) for v in vals]
                    scal = [v for v in vals if _scalar_key(v) is not None or v is None]
                    if len(scal) != len(vals):
                        continue  # nested values: covered by recursion below
                    counts: dict[Any, int] = {}
                    for v in scal:
                        counts[v] = counts.get(v, 0) + 1
                    desc = f"{key}: {len(counts)} distinct"
                    if len(vals) < len(objs):
                        desc += f", present in {len(vals)}"
                    nums = [
                        v
                        for v in scal
                        if isinstance(v, (int, float)) and not isinstance(v, bool)
                    ]
                    if nums and len(nums) == len(scal):
                        desc += f", range {min(nums)}..{max(nums)}"
                    if len(counts) == len(objs):
                        desc += " (unique per element)"
                    elif len(counts) <= _STATS_MAX_DISTINCT_LISTED and all(
                        not isinstance(v, str) or len(v) <= 60 for v in counts
                    ):  # categories, not free text
                        top = sorted(counts.items(), key=lambda kv: -kv[1])[
                            :_STATS_TOP_VALUES
                        ]
                        shown = ", ".join(
                            f"{json.dumps(v, ensure_ascii=False)[:40]}×{n}"
                            for v, n in top
                        )
                        desc += f", top: {shown}"
                    fields.append(desc)
                if fields:
                    lines.append(f"{path}/* ({len(node)} items): " + "; ".join(fields))
            for i, child in enumerate(node[:1]):
                visit(child, f"{path}/*", depth + 1)

    visit(data, "", 0)
    return lines


def is_skeleton_mode(working_json: Any) -> bool:
    """True when the document is too large to inline even compactly, so the
    prompt carries a skeleton (and lookup tools are offered, ADR-0024)."""
    max_inline = get_settings().llm_max_inline_chars
    compact = json.dumps(
        working_json, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return len(compact) > max_inline


def _inline_context(working_json: Any) -> str:
    """Whole document, pretty-printed when that fits the inline cap."""
    max_inline = get_settings().llm_max_inline_chars
    pretty = json.dumps(working_json, indent=2, ensure_ascii=False, default=str)
    if len(pretty) <= max_inline:
        return f"CURRENT WORKING JSON:\n{pretty}"
    compact = json.dumps(
        working_json, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return f"CURRENT WORKING JSON:\n{compact}"


def _skeleton_context(working_json: Any) -> str:
    skeleton = json.dumps(
        build_skeleton(working_json),
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    return (
        "The working JSON is too large to inline in full. Below is a "
        "STRUCTURAL SKELETON: EVERY key that occurs anywhere in the "
        "document, with SAMPLE values — long strings are truncated with "
        "an ellipsis. Each array shows ONE sample element whose keys are "
        'merged from ALL its elements ("…keys in only some items" lists '
        'keys that only some elements have) plus a "…+N more items" '
        "marker (so N+1 is the array length); arrays whose elements "
        'carry "$type" show one merged sample per $type, with counts.\n'
        f"{skeleton}\n"
        "You may rely on the keys and the sample values shown. For "
        "large arrays you can see only the first element's shape, so "
        "NEVER guess values you cannot see: for any change that targets "
        "elements by a field value, a range, or every element, use a "
        '"bulk" op (see BULK EDITS) — the server matches it against the '
        "full document. Only use plain diffs for paths and values "
        "visible above."
        + (
            "\nARRAY FIELD STATS (computed over EVERY element — use them "
            'to pick the right "where" field: a field that is not '
            "unique per element, e.g. a counter restarting per group, "
            'cannot identify positions; use "$index" for "first N" '
            "requests):\n" + "\n".join(stats)
            if (stats := build_array_stats(working_json))
            else ""
        )
    )


def build_system_prompt(
    working_json: dict[str, Any],
    has_history: bool = False,
    *,
    mode: str | None = None,
) -> str:
    """Build the system prompt with the working JSON inlined.

    `has_history` adds the conversation-history rules (diff status
    semantics) when prior turns are replayed alongside this prompt.

    `mode` is chosen by the turn planner (ADR-0025): "inline" or
    "skeleton". None = size-based choice against LLM_MAX_INLINE_CHARS.
    Format notes are always matched on the document given.
    """
    if mode is None:
        mode = "skeleton" if is_skeleton_mode(working_json) else "inline"
    if mode == "skeleton":
        context = _skeleton_context(working_json)
    else:
        context = _inline_context(working_json)
    notes = format_notes_block(working_json)
    if notes:
        context = f"{context}\n\n{notes.rstrip()}"
    return _TEMPLATE.replace("__CONTEXT__", context).replace(
        "__HISTORY__", _HISTORY_RULES if has_history else ""
    )
