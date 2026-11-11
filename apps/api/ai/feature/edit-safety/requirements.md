# Backend Requirements — Edit Safety (PRD A)

Only what the **server / API layer** must implement. Web impact: none beyond
showing the existing `failure_reason` on failed diffs (already rendered).
Status: draft 2026-11-10. Plan → implementation → tasks follow this doc.

---

## 0. Problem — issues this PRD addresses

| ID | Issue | Evidence |
|----|-------|----------|
| I-A1 | **Data loss: truncated previews written back as full values.** In skeleton mode, long strings are shown cut (`prompting.py:275`, `str_cap` + `…`) and tool results are cut (`json_tools.py:44`, `:207`, `:234`). The model copies the preview, edits it, and returns it as `new_value`. `_apply_one` writes it unchecked. | Local repro 2026-11-10 on a 166 KB user document (gemma4:12b), typo-fix prompt: 3/3 runs. `/data/description` 7485 → 80 chars; `/data/character_book/entries/40/content` 1273 → 159. The explanation only mentioned a one-word typo fix. |
| I-A2 | **No partial string edit.** Every diff replaces a whole value, so fixing one word in a 7k-char field means re-emitting 7k chars (output cost, latency, and it invites I-A1). | Same repro; prod lorebook sessions with 1–3k-char entries. |
| I-A3 | **`read` cannot see past 4000 chars.** `JsonToolbox.read` truncates at `chat_tool_result_max_chars`; there is no way to read the rest. | Prod 2026-11-09: `read /data/description` → `result_chars=4012`, field is 7485 chars. |
| I-A4 | **Silent "reviewed, no changes" turns.** Model claims it reviewed content, returns 0 diffs, user can't tell what was actually read. | Prod 2026-11-10 lorebook session: two turns "successfully read and analyzed…", `diffs=0`; the user complained the assistant kept repeating its progress report. |

## Goals

- No diff can shrink a value by copying a preview.
- Small text edits cost tokens proportional to the edit, not the field.
- The model can read any string in full, page by page.
- The user sees what a turn actually looked at.

## Non-goals

- Semantic validation of edits (does the rewrite preserve meaning).
- JSON Schema validation (still out of scope per CLAUDE.md).

---

## 1. Truncation guard — `diff_utils.py`

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| ES-01 | `_apply_one` (and therefore `apply_all_verbose`) rejects a `modify`/`add` diff with `DiffApplyError("truncated preview copied")` when `new_value` is a string that ends with a **preview marker** (`…`, `…(truncated)`, `…+N more items`) **and** the current value at that path is a longer string. | MVP | I-A1 |
| ES-02 | Same rule applied recursively: a `new_value` object/array containing any string leaf that ends with a preview marker, where the same leaf exists in the old value and is longer, is rejected. Covers the model rewriting a whole entry object. | MVP | I-A1 |
| ES-03 | Marker list is one module constant shared with `prompting.py` and `json_tools.py` (single source; producers import it). | MVP | I-A1 |
| ES-04 | A string that legitimately ends with `…` and is **not** shorter than the old value (or the path is new) is allowed. | MVP | I-A1 |
| ES-05 | Rejected diffs go through the existing failed path: `status="failed"`, `failure_reason="truncated preview copied — read the full value first"`, no `diff` SSE event (ADR-0021 H-04 unchanged). | MVP | I-A1 |
| ES-06 | Bulk-expanded diffs (`bulk_edits.py`) pass through the same guard. | MVP | I-A1 |
| ES-07 | INFO log per rejection: `edit guard rejected path=%s old_len=%d new_len=%d`. No values at INFO (ADR-0017). | MVP | I-A1 |
| ES-08 | **Marker-less copies** (found in the live repro: models drop or rewrite `…`, e.g. `...)`): a `new_value` string ≤ 85 % of a ≥ 120-char old value is rejected when its ending matches (fuzzy, ratio ≥ 0.6) a passage that stops before the last 15 % of the old value. Exact-substring probe at any size; fuzzy scan only for old ≤ 50k chars. Deliberate "cut this text in half" edits are refused too (fail-safe). | MVP | I-A1 |

**Hotfix status (2026-11-10, branch `hotfix/edit-guard-transient-retry`):** ES-01…08 shipped (guard in `apply_all_verbose` via `check_truncation`; markers in `preview.py`). Live repro (card, gemma4:12b): `/data/description` 7577→87 and `/data/scenario` 620→84 rejected, document unchanged.

## 2. Prompt rules — `prompting.py`, `json_tools.py` INSTRUCTIONS

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| ES-10 | New system-prompt rule (skeleton + tools modes): "Values ending in `…` are previews, never edit sources. To change part of a long string use `edit_text`; to rewrite it, `read` the full value first." | MVP | I-A1, I-A2 |
| ES-11 | Tool results that truncate say so explicitly with remaining length and how to continue: `"…(truncated, 3485 more chars — read with offset=4000)"`. | MVP | I-A3 |

## 3. `edit_text` operation — partial string edit

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| ES-20 | New diff operation `edit_text`: `{"path", "operation": "edit_text", "find": str, "replace": str, "occurrence"?: int \| "all"}`. Target must be a string. Default `occurrence=1`. | MVP | I-A2 |
| ES-21 | Server expands `edit_text` into a normal `modify` diff (`old_value` = full current string, `new_value` = edited string) before apply, so DiffViewer, history, accept/reject and revert are unchanged. Expansion lives beside `bulk_edits.py` (same expand-then-apply pattern, ADR-0022). | MVP | I-A2 |
| ES-22 | `find` not found → failed diff, `failure_reason="text not found"`. `find` matches more than once with `occurrence=1` → apply the first and note `matches=N` in the explanation summary. | MVP | I-A2 |
| ES-23 | `find` must be ≥ 3 chars and ≤ 2000 chars; `replace` ≤ 20 000 chars. Violations → failed diff. | MVP | I-A2 |
| ES-24 | `edit_text` allowed with bulk patterns: `/entries/*/content` + `where` + `find`/`replace` → one `edit_text` per match (capped by `bulk_max_matches`). | Later | I-A2 |
| ES-25 | History replay (ADR-0021 C-03) serialises the expanded diff compactly as `{"operation":"edit_text","find","replace","status"}` instead of the full old/new strings. | MVP | I-A2 |
| ES-26 | Output contract in the prompt documents `edit_text` with one example; rule: "prefer `edit_text` for changes inside strings longer than 200 chars". | MVP | I-A2 |

## 4. Paged `read` — `json_tools.py`

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| ES-30 | `read(path, offset?, length?)`: for string values, returns `text[offset:offset+length]` (default `offset=0`, `length=chat_tool_result_max_chars`), plus `total_chars` and `next_offset` (null at end). | MVP | I-A3 |
| ES-31 | For objects/arrays, behaviour unchanged (truncate serialised JSON), but the truncation note names the largest child paths so the model can read them individually. | MVP | I-A3 |
| ES-32 | Tool schema (`JsonToolbox.schemas()`) documents `offset`/`length`. | MVP | I-A3 |

## 5. Turn transparency

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| ES-40 | `complete` SSE payload gains `read_summary: {paths: [str], chars: int, truncated_paths: [str]}` listing every path the tool loop read this turn (max 50 listed, then `"+N more"`). Absent in inline mode. | MVP | I-A4 |
| ES-41 | When the user message is an edit request (intent ≠ question, PRD C intent classifier; until then: always) and the turn ends with 0 diffs after ≥ 1 tool read, the server appends to the explanation: "No changes were made. Read: <paths>." | MVP | I-A4 |

---

## Spec / model changes (`openapi/spec.yaml` first, then `models.py`, then TS mirrors)

- `DiffOperation` enum: add `edit_text` (request-side only; stored diffs are always expanded `modify`).
- `DiffEntry`: optional `find`, `replace`, `occurrence` (present only when the source op was `edit_text`).
- `ChatCompleteEvent`: optional `read_summary`.
- `failure_reason` values documented: `truncated preview copied`, `text not found`.

## Acceptance

- Replaying the 2026-11-10 repro (synthetic copy, see Tests) never shortens a field via a preview: 0/10 runs.
- A one-word typo fix on a 7k-char field produces an `edit_text`-sourced diff and ≤ 300 completion tokens.
- `read` with `next_offset` reaches the end of a 20k-char string.

## Tests

- Unit: guard (marker + shorter → fail; marker + new path → ok; nested object leaf; bulk-expanded), `edit_text` expansion (found / not found / multiple / limits), paged read.
- Live eval (`LIVE_LLM=1`, Ollama): **synthetic** character card (structure like chara_card_v2, invented text — never user data) with a 7k-char description and 80 lorebook entries; "fix typos" must not shrink any field.

## Excluded

- Fuzzy `find` matching (whitespace-insensitive). Revisit if the live eval shows frequent `text not found`.
- Regex `find`.

---

Ship order: ES-01…ES-07 first as a hotfix (data loss in prod), the rest with PRD B.
Related: ADR-0021 (history), ADR-0022 (bulk), ADR-0024 (tools). New ADR needed: `edit_text` op + truncation guard.
