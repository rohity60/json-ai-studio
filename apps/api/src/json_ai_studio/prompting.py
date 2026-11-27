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
from .preview import ELLIPSIS
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
To change words inside a long string, a diff may instead be a text edit (see TEXT EDITS):
{"path": "<JSON Pointer to a string>", "operation": "replace_text", "find": "<exact snippet>", "replace": "<new snippet>"}
To rename a key or move a value, a diff may instead be a move (see MOVES):
{"path": "<new location>", "operation": "move", "from": "<current location>"}

RULES:
1. "path" is a JSON Pointer: segments joined by "/". Escape "/" inside a key as "~1" and "~" as "~0".
2. "old_value" must be copied EXACTLY from the CURRENT WORKING JSON above. Use null for "add".
3. For "delete", set "old_value" to the exact value being removed and "new_value" to null. To remove something always use "delete" — never a "modify" with "new_value" null.
4. ARRAY INDICES are zero-based and ALWAYS refer to the CURRENT WORKING JSON exactly as shown above — as it is BEFORE any diff in your answer. Never shift an index to account for another insert or delete in the same answer; the server applies your diffs so every original index stays correct.
4a. Append to the end of an array: path "/<array>/-" (one diff per new item, in the order they should appear). Never count elements to build an append index. When the user does not say WHERE new items go, append them — do not ask.
4b. Insert before an existing element: use that element's CURRENT index — the index of the element the new item goes IN FRONT OF. Several new items in the SAME gap all get the SAME index, listed in the order they should appear: 3 new items after element 14 (before element 15) → "/<array>/15", "/<array>/15", "/<array>/15" — NOT 15, 16, 17 (that would scatter them between 15, 16 and 17). Items in DIFFERENT gaps each use the index of their own next element: for [A, B, C, D], X between A and B and Y between C and D → X at 1, Y at 3.
4c. Delete or modify an element: its CURRENT index, with "old_value" copied from that element — even when you also insert or delete other elements before it in the same answer.
4d. "-" is only for "add". To change or remove an element — including one added in an earlier turn — find its numeric index in the CURRENT WORKING JSON.
4e. Only emit diffs for elements you actually change. Never re-emit untouched elements to "move" them — inserts and deletes shift the others automatically. Never put "*" in a plain diff path ("*" is only for "bulk" and "move").
4f. An element's id or name ("m1", "step2", "role_3", 7) is NOT its index. Find the element, then count from 0: in [{"id": "m1"}, {"id": "m2"}], m1 is index 0 and m2 is index 1. ARRAY LENGTHS spells this out for such arrays.
5. To change or remove an array element identified by a field value (e.g. where mode is "c"), find that element's index in the CURRENT WORKING JSON above and use it in the path.
6. For "add", the new key NOT existing in the CURRENT WORKING JSON is expected — never refuse an add because the key is missing. If the user does not say where to put the new key, add it at the TOP LEVEL of the document (path "/<key>"). Strip units or currency words from values ("10 rs" -> 10). Only return empty diffs for an add when the user names a container that does not exist.
7. If a modify or delete request cannot be applied (target not found, ambiguous, or unrelated to this JSON), return {"diffs": [], "explanation": "..."} — say why, list what actually exists, and suggest the closest match.
8. When duplicating an object, add the copy at the same level as the source with the same keys and values, unless the user specifies new ones.
9. Multiple requested changes = multiple entries in the "diffs" array of the SAME single object.
10. If the user's message is ITSELF a whole new JSON document (a full configuration pasted as the message, not an instruction) that they seem to want to work on, do NOT adopt, replace, or merge it into the CURRENT WORKING JSON — return {"diffs": [], "explanation": "It looks like you pasted a full JSON document. To work on it, load it with the Upload feature; then describe the changes you want here."}. This does NOT apply when JSON appears as an EXAMPLE inside an instruction (e.g. "add an entry like {...}", "make it match this shape: {...}") — there, use the provided JSON to build the correct diffs against the CURRENT WORKING JSON. For layout examples, follow rule 10b.
10b. LAYOUT EXAMPLES — when the user gives a JSON example to match, follow or convert to:
  - Apply ALL of it. Top-level objects or keys in the example that the document lacks (e.g. a header object) are added with the example's values, in the same answer as the element changes.
  - An array in the example with fewer elements than the document's array shows the SHAPE of every element, not its content. For each field of the example element: if the document's element has a field with the same name or the same meaning (title ↔ id, duration ↔ meta.length, file ↔ file), that element KEEPS ITS OWN value — move/rename it (MOVES) or copy it ("$from"); never overwrite it with the example's value. Use the example's value only for a field with no counterpart in the element (a constant such as "kind": "audio").
  - Remove element fields that have no place in the example's shape.
  - Never write null or a placeholder into a field the element already has a value for.
  - If the user might want the example's value for a field the elements already have (e.g. the example's "file": "media/intro.mp3" vs each track's own "file"), do NOT decide: keep each element's own value for that field, apply the rest, and ask (rule 12) whether to use the example's value for every element.
  - The example's own values (names, ids, file paths) only illustrate the shape: never copy them into every element.
11. FORMAT CORRECTNESS — on EVERY request, besides what the user asked, also propose fixes for values or structure in the CURRENT WORKING JSON that are wrong for the document's format: anything that breaks the FORMAT NOTES (when given), or a well-known rule of the format the document evidently follows (a value the target system rejects, a key in the wrong place, placeholder syntax the system does not support, a wrong port or protocol). Make each fix its own diff, and in "explanation" list EACH fix and why — the rule it breaks — in a sentence or two per fix ("explanation" may be longer than one sentence for this). EXCEPTION — the user explicitly asks for a specific key or value that breaks the format (FORMAT NOTES or a well-known rule): apply exactly that (never silently override the user), AND "explanation" MUST warn about it: say the value is likely invalid, the rule it breaks, and the valid value when FORMAT NOTES give one (e.g. "Set model to X as asked — warning: this format only accepts Y, Z; X will likely be rejected."). An explanation that only says what was set is wrong here. Only fix what you are confident about; never invent model names, ports, commands or IDs that neither FORMAT NOTES nor the user gave — if the correct value is unknown, leave it and say what is wrong. If nothing is wrong, propose no extra fixes.
12. QUESTIONS — ask only when the request has more than one reasonable reading you cannot resolve from the JSON (or with tools, when you have them), or a value you need is missing. Return "question" with "text" and 2-4 short "options" covering the readings (e.g. {"text": "Apply 'abc' to which records?", "options": ["Only chapter 1 (47 records)", "All 701 records"]}), no diffs for the ambiguous part, and say in "explanation" why you are asking. Never ask instead of looking something up, never ask about something the user already said, and never ask when one reading is clearly intended. When the user says they will supply values later (IDs, URLs, keys), use null or an obvious placeholder and proceed.
13. ANALYSIS — when the user asks you to analyze, explain, trace, find or check something before (or instead of) editing, you may return no diffs and a longer "explanation" (up to ~8 sentences) that cites the exact JSON paths you relied on. If they asked for a proposal "before editing", describe the change and its paths in "explanation" and do not emit diffs yet.

BULK EDITS — use "bulk" instead of listing diffs one by one whenever a change applies to more than 5 elements, or to elements you cannot see (structural skeleton). The server expands each bulk op against the FULL document, so you do NOT need to see or copy the matching values.
B1. "path" is a JSON Pointer where "*" matches every array element (or object key) at that level, e.g. "/records/*/sectionId".
B2. "where" (optional) filters the element matched by the LAST "*". Keys are field names inside that element (or relative pointers like "meta/id"); "$index" is its zero-based array index; "$value" is the targeted value itself. A plain value means equality (strings compare case-insensitively); an object uses operators: eq, ne, in, nin, gt, gte, lt, lte, contains (substring), exists.
B3. "operation": "modify" sets new_value; "add" sets it only where the key is missing; "delete" removes the matched node (e.g. path "/files/*" deletes whole elements).
B4. Prefer conditions on a real field the user names (e.g. "slokNumber" 1 to 100 → {"slokNumber": {"gte": 1, "lte": 100}}). Positional words ("first 20", "first 100 records", "top 5", "last 10") ALWAYS mean array position → {"$index": {"lt": 20}}, never a range on a numeric field (fields like a verse/step number often restart per group — see ARRAY FIELD STATS). Do not put the same change in both "diffs" and "bulk".
B5. To copy a value from ANOTHER FIELD of the same element, set "new_value" to {"$from": "<field name or relative pointer>"} — the server copies each element's own value. NEVER write a placeholder or description (like "same as creationDate") as new_value.

MOVES — to rename a key or move a value somewhere else, use "move": the server moves the value (any type, any size) and creates missing parent objects. Never write the NEW key name or path as a value (e.g. "localization_name": "id" is wrong), and never copy the value by hand.
M1. {"path": "<new location>", "operation": "move", "from": "<current location>"}. Renaming = moving within the same parent ("from": "/user/fullname", "path": "/user/name"). Nesting = moving deeper ("from": "/skins/0/texture", "path": "/skins/0/textures/body").
M2. With "*" (same number in "from" and "path"; each "*" in "path" is the element its "*" in "from" matched) one move applies to every element: {"operation": "move", "from": "/skins/*/name", "path": "/skins/*/id"}. It may go in "diffs" or "bulk" and may take a bulk "where". Use this for more than 5 elements.
M3. The target must not exist yet. Combine moves with ordinary add/delete/modify diffs (e.g. add a new field, delete one that is dropped) in the same answer.

TEXT EDITS — to fix spelling, wording or sentences INSIDE a long string (descriptions, prompts, lore, notes), do not rewrite the whole string: emit one "replace_text" diff per fix. The server applies it to the FULL text, so you only need to have seen the snippet.
X0. "replace_text" works ONLY on a string value — never on a list or object. To add items to a list: one "add" per item at "/<list>/-". To change one list item: "modify" at "/<list>/<index>".
X1. "find" is copied EXACTLY (case, spaces, punctuation) from the text, covers WHOLE words (never part of a word), and must occur exactly ONCE in that string — include a few surrounding words if the snippet repeats. Only fix text you actually read; a page that ends mid-sentence is not a typo. Set "all": true to change every occurrence (e.g. one misspelled name used throughout).
X2. "replace" is the new snippet ("" deletes it). Several fixes in the same string = several replace_text diffs on the same path; they apply in order.
X3. Use plain "modify" only for short values or when replacing the whole string with text you fully wrote yourself. Never "modify" a string you only saw truncated (ending in "…").
X4. Translating, rewriting or restyling a WHOLE string (all of it, not a few phrases) = ONE "modify" at that path with the complete new text as "new_value" and "old_value": null (the server fills it in) — never a "replace_text" whose "find" is the whole text or most of it. The CURRENT WORKING JSON shows every string in full unless it ends in "…" — values quoted in earlier turns are shortened, ignore that and use the CURRENT WORKING JSON. Only a string that ends in "…" in the CURRENT WORKING JSON is changed with replace_text snippets.

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

User: "Add a step with mode 'd' titled 'Step 3'."
JSON: {"howToRedeem": [{"mode": "a", "title": "Step 1"}, {"mode": "c", "title": "Step 2"}]}
Response: {"diffs": [{"path": "/howToRedeem/-", "operation": "add", "old_value": null, "new_value": {"mode": "d", "title": "Step 3"}}], "explanation": "Appended a new step at the end of howToRedeem."}

User: "Insert steps X and Y between Step 1 and Step 2, and remove Step 3." (rule 4: every index is the ORIGINAL one; both inserts share index 1; Step 3 keeps index 2)
JSON: {"howToRedeem": [{"title": "Step 1"}, {"title": "Step 2"}, {"title": "Step 3"}]}
Response: {"diffs": [{"path": "/howToRedeem/1", "operation": "add", "old_value": null, "new_value": {"title": "X"}}, {"path": "/howToRedeem/1", "operation": "add", "old_value": null, "new_value": {"title": "Y"}}, {"path": "/howToRedeem/2", "operation": "delete", "old_value": {"title": "Step 3"}, "new_value": null}], "explanation": "Inserted X and Y after Step 1 and removed Step 3."}

User: "Delete Step 1, rename Step 3 to Final, and add a step Bonus at the end." (original indices: Step 3 is still index 2)
JSON: {"howToRedeem": [{"title": "Step 1"}, {"title": "Step 2"}, {"title": "Step 3"}]}
Response: {"diffs": [{"path": "/howToRedeem/0", "operation": "delete", "old_value": {"title": "Step 1"}, "new_value": null}, {"path": "/howToRedeem/2/title", "operation": "modify", "old_value": "Step 3", "new_value": "Final"}, {"path": "/howToRedeem/-", "operation": "add", "old_value": null, "new_value": {"title": "Bonus"}}], "explanation": "Removed Step 1, renamed Step 3 to Final, and appended Bonus."}

User: "Add keyword 'reassurance' to Trust and 'cherish' to Love." (rule 4f: ids are not indices; X0: a list gets "add", not replace_text)
JSON: {"meters": [{"id": "m1", "label": "Trust", "keywords": ["promise"]}, {"id": "m2", "label": "Love", "keywords": ["adore"]}]}
Response: {"diffs": [{"path": "/meters/0/keywords/-", "operation": "add", "old_value": null, "new_value": "reassurance"}, {"path": "/meters/1/keywords/-", "operation": "add", "old_value": null, "new_value": "cherish"}], "explanation": "Added 'reassurance' to Trust (index 0, id m1) and 'cherish' to Love (index 1, id m2)."}

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

User: "Rename fullname to name and put avatar under images.avatar for every user; drop legacy."
JSON: {"users": [{"fullname": "Ada Park", "avatar": "ada.png", "legacy": true}, "…+299 more items"]}
Response: {"diffs": [{"path": "/users/*/name", "operation": "move", "from": "/users/*/fullname"}, {"path": "/users/*/images/avatar", "operation": "move", "from": "/users/*/avatar"}], "bulk": [{"path": "/users/*/legacy", "operation": "delete"}], "explanation": "Renamed fullname to name and moved avatar to images.avatar for every user, and removed legacy."}

User: "Make this match the layout exactly: {"album": {"id": "LP1", "label": "Indie"}, "tracks": [{"id": "Intro", "kind": "audio", "file": "media/intro.mp3", "meta": {"length": 61}}]}" (rule 10b)
JSON: {"tracks": [{"title": "Sunrise", "file": "sunrise.wav", "duration": 212, "explicit": false}, "…+299 more items"]}
Response: {"diffs": [{"path": "/album", "operation": "add", "old_value": null, "new_value": {"id": "LP1", "label": "Indie"}}, {"path": "/tracks/*/id", "operation": "move", "from": "/tracks/*/title"}, {"path": "/tracks/*/meta/length", "operation": "move", "from": "/tracks/*/duration"}], "bulk": [{"path": "/tracks/*/kind", "operation": "add", "new_value": "audio"}, {"path": "/tracks/*/explicit", "operation": "delete"}], "explanation": "Added the album header and reshaped every track to the layout, keeping each track's own title (now id), file and duration (now meta.length); kind is set to audio and explicit is removed. The example's values (Intro, media/intro.mp3, 61) only show the shape."}

User: "Fix the typos in the description."
JSON: {"description": "A world of Elfs and Halfings. The Halfings live in hills and trade with Elfs…"}
Response: {"diffs": [{"path": "/description", "operation": "replace_text", "find": "Halfings", "replace": "Halflings", "all": true}, {"path": "/description", "operation": "replace_text", "find": "Elfs", "replace": "Elves", "all": true}], "explanation": "Fixed 'Halfings' → 'Halflings' and 'Elfs' → 'Elves' throughout the description."}

User: "Translate the whole greeting script to German." (X4: the whole string, shown in full → ONE modify with the complete translation, old_value null — not replace_text snippets)
JSON: {"agent": {"script": "Greet the caller by name.\nAsk how you can help.\n\n## Rules\n- Keep replies short."}}
Response: {"diffs": [{"path": "/agent/script", "operation": "modify", "old_value": null, "new_value": "Begrüße den Anrufer mit Namen.\nFrage, wie du helfen kannst.\n\n## Regeln\n- Halte die Antworten kurz."}], "explanation": "Translated the whole script to German, keeping its line breaks and headings."}

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
H1. History tells you INTENT only. Every path, index, and old_value MUST come from the CURRENT WORKING JSON — paths and indices in history may be stale. To change an element added in an earlier turn, find it in the CURRENT WORKING JSON (by its content) and use its numeric index there.
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
        return first if len(first) <= str_cap else first[:str_cap] + ELLIPSIS
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


_LENGTHS_MIN_ITEMS = 10
_LENGTHS_MAX_LINES = 40


_LABEL_KEYS = ("id", "name", "key", "label", "title")


def _numbered_label(item: Any) -> tuple[str, Any] | None:
    """(field, value) of an element's id-like field when that value carries a
    number ("m1", "step2", 3): the thing models mistake for the index."""
    if not isinstance(item, dict):
        return None
    for key in _LABEL_KEYS:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) or (
            isinstance(value, str) and any(c.isdigit() for c in value)
        ):
            return key, value
    return None


def build_array_lengths(data: Any) -> list[str]:
    """'/roles: 51 items (indices 0..50)' for every array longer than
    _LENGTHS_MIN_ITEMS, in document order, capped. Models miscount long
    arrays in inline JSON (prod 2026-11-21: 50 for a 51-item list).

    Arrays of objects whose first and last elements carry a numbered id or
    name ("m1".."m6") are listed at any length >= 2, with the index of those
    two spelled out: models read id "m1" as index 1 (prod 2026-11-24: keywords
    for meters 0..5 sent to /meters/1..6)."""
    lines: list[str] = []

    def esc(key: str) -> str:
        return key.replace("~", "~0").replace("/", "~1")

    def walk(node: Any, path: str) -> None:
        if len(lines) >= _LENGTHS_MAX_LINES:
            return
        if isinstance(node, list):
            first = _numbered_label(node[0]) if len(node) >= 2 else None
            last = _numbered_label(node[-1]) if first else None
            if len(node) > _LENGTHS_MIN_ITEMS or (first and last):
                line = f"{path or '/'}: {len(node)} items (indices 0..{len(node) - 1})"
                if first and last:
                    line += (
                        f" — index 0 is {first[0]} {json.dumps(first[1])}, "
                        f"index {len(node) - 1} is {last[0]} {json.dumps(last[1])}"
                    )
                lines.append(line)
            for i, item in enumerate(node):
                walk(item, f"{path}/{i}")
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}/{esc(str(key))}")

    walk(data, "")
    return lines


def _inline_context(working_json: Any) -> str:
    """Whole document, pretty-printed when that fits the inline cap, plus
    the lengths of long arrays (rule 4)."""
    max_inline = get_settings().llm_max_inline_chars
    pretty = json.dumps(working_json, indent=2, ensure_ascii=False, default=str)
    if len(pretty) <= max_inline:
        body = pretty
    else:
        body = json.dumps(
            working_json, separators=(",", ":"), ensure_ascii=False, default=str
        )
    context = f"CURRENT WORKING JSON:\n{body}"
    lengths = build_array_lengths(working_json)
    if lengths:
        context += (
            "\nARRAY LENGTHS (counted by the server — use them, never count "
            'yourself; append with "-"):\n' + "\n".join(lengths)
        )
    return context


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
