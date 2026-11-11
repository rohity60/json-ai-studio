# Web Requirements — Turn Planner & Turn Resume (PRD B, client side)

Only what the **frontend** must implement. Server side:
`apps/api/ai/feature/turn-planner/requirements.md`. Status: draft 2026-11-10.

## Issues addressed

| ID | Issue |
|----|-------|
| I-B5 | A failed turn shows a generic error; all progress (tool rounds, waits) is lost; the user re-types or re-sends. |
| I-B6 | After a failure the user has no way to continue the same request. |
| I-B1 | Users wait minutes with no idea how long a turn will take. |
| I-B11 | Provider content refusals look like crashes. |
| I-B13 | Long turns (2–7 min on the free tier) look frozen: one status line, no plan, no step count, no reason for waits. |

## Requirements

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| WB-01 | `ChatPanel` handles SSE `plan` `{mode, max_rounds, eta_s}`: shows "Estimated ~N s" under the thinking indicator; hidden when `eta_s < 10`. | MVP | I-B1 |
| WB-02 | SSE `error` with `turn_id` + `resumable: true` renders the failed assistant message with a **Continue** button → `POST /api/sessions/{id}/turns/{turnId}/resume`, consumed by the same SSE handler as `/api/chat`. | MVP | I-B5, I-B6 |
| WB-03 | Continue is shown only on the latest failed turn; disabled while any stream is active; hidden after success (server returns 409 on repeat). | MVP | I-B5 |
| WB-04 | Failed turns from `conversation_history` (`status: failed`) render with a muted "attempt failed" badge and the read paths summary if present. | MVP | I-B6 |
| WB-05 | `error.code = "safety_block"` → distinct message: "The AI provider declined this request." No retry/continue button. | MVP | I-B11 |
| WB-06 | TS mirrors (`lib/api.ts` types): `ChatTurn.status`, `error_code`; SSE `plan`, `progress`, `retrying`, `waiting.reason`, `tool.message`; `resumeTurn()` client fn. Hand-written per CLAUDE.md. | MVP | — |
| WB-07 | IndexedDB mirror (ADR-0014) stores the new turn fields as-is; no resume after backend restart (trace is server memory only) — Continue hidden when the server 404s. | MVP | I-B5 |
| WB-08 | **Progress panel** inside the pending assistant bubble: header from `plan.message`; a step line *"Step 2/5 · Reading /data/description"* with a thin progress bar (`step/steps`); a list of finished steps with ✓ (each `tool.message`, retries as ⚠ lines). Replaces the single `toolStatus` string in `SessionContext`. | MVP | I-B13 |
**Status: WB-08…WB-12 shipped (branch `feature/turn-progress`, 2026-11-11):** `lib/progress.ts` (event fold), `TurnProgressPanel` in `ChatPanel`; older backends fall back to WB-08a text.

| WB-08a | **Hotfix 2026-11-11 (shipped):** `SessionContext` keeps the last tool step and the current wait separately, so a wait no longer hides the tool step: "✓ Searching the document for “x”" + "Waiting for AI model capacity… ~45s". Superseded by WB-08. | MVP | I-B13 |
| WB-09 | Waits: show `waiting.message` with a **client-side countdown** that ticks every second from `retry_after` (server ticks every 5 s); reason icon for pacing / limit / cooldown. | MVP | I-B13 |
| WB-10 | `retrying` → amber line *"Temporary AI provider error — retrying (1/3)"*; never shown as a failure unless the turn ends in `service_unavailable`. | MVP | I-B13 |
| WB-11 | On `complete`, the panel collapses to *"Done in 3 min 41 s · 5 steps"* with a "Show steps" toggle; steps live in UI state only until B-57 stores them server-side. | MVP | I-B13 |
| WB-12 | Unknown `stage` / missing fields fall back to today's text; no layout shift on mobile (panel max 4 visible lines, scrolls). | MVP | I-B13 |

## Excluded

- Auto-retry from the client. Retries are server policy (PRD B §3).
