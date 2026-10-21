# 0023-format-hints-and-proactive-format-fixes

**Date**: 2026-10-21
**Status**: Accepted

## Context

Prod chat 2026-10-19: a user's Zoom Rooms Controls profile had an invalid adapter `model` ("GenericNetworkDevice"). Asked to "make this code work with qsys", the model changed it to "Q-SYS Core110f" — also invalid — and left other format errors (`methods` outside `ports[]`, `{{…}}` placeholders, `sg` as a command). Local replays reproduced it on gemma4:12b ("Q-SYS Core", "Q-SYSCore"). A prompt rule permitting fixes on request did not help: the model lacked the format's rules, not the permission.

## Decision

1. **Format hints from template metadata.** Templates may declare `formatSignature` — JSON Pointers with `*` (e.g. `/adapters/*/model`, `/adapters/*/ip`). `apps/web/scripts/export-format-notes.mjs` exports each such template's `requiredFields` + `optionalFields` + `bestPractices` to `apps/api/src/json_ai_studio/config/format_notes.json` (committed). `format_hints.py` injects them as **FORMAT NOTES** into the system prompt when every signature pointer resolves in the working JSON (max 2 formats). Hand-written template docs become the model's reference; no second copy of the rules is maintained.
2. **Proactive format correctness (prompt rule 11).** On every request the model also proposes fixes for values/structure that break FORMAT NOTES or a well-known rule of the evident format, one diff per fix, each explained in `explanation` (no per-diff field). **Exception:** an explicit user request for a specific key/value is applied as asked, with a warning. Never invent values neither FORMAT NOTES nor the user gave.
3. **Bulk safety** (found by the live evals): operator aliases (`neq`, `!=`, `>=`, …) and a guard refusing bulk modifies that replace a list/object with a scalar or vice versa (except `$from` copies).

## Consequences

- Live (local gemma4:12b): Zoom prod case 0/2 → 2/2 `GenericNetworkAdapter`; explicit invalid value applied with warning; proactive npm fixes explained; valid docs untouched. Chat-history live suite: no regressions (9/12 overall; the 3 failures pre-date this change on 12b).
- Users get unrequested fix diffs on documents with format errors; each is a separate pending diff they can reject.
- `format_notes.json` must be regenerated when a signed template changes (a test fails on drift).
- Only the Zoom template is signed so far; adding signatures to other templates extends coverage.

## References
- Research: `apps/web/ai/feature/templates/research/zoom-rooms-qsys.md`
- ADR-0019/0020 (templates), ADR-0022 (bulk edits)
- Tests: `tests/test_suggested_fixes.py`, `tests/test_suggested_fixes_live.py`, `tests/test_bulk_edits.py::TestBulkRobustness`
