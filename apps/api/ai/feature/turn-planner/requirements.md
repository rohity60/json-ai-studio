# Backend Requirements — Turn Planner, Provider Policy & Turn Resume (PRD B)

Only what the **server / API layer** must implement. Client side:
`apps/web/ai/feature/turn-planner/requirements.md`.
Status: draft 2026-11-10. Amends ADR-0025 (deployment token budget), ADR-0021 (chat history).

---

## 0. Problem — issues this PRD addresses

| ID | Issue | Evidence |
|----|-------|----------|
| I-B1 | **Planner only checks the first call.** `turn_planner.plan_turn` sizes call 1 against `tpm_input_limit × headroom`; `max_rounds` is always `chat_tool_max_rounds` (4). Each tool round resends the whole conversation, growing every round. | Prod 2026-11-10 lorebook: rounds 8127 → 8518 → 8874 → 9187 → 9535 tokens; each > half of 12 800, so 1 call/min; turn took **272 s, 44 241 prompt tokens** to read 4 entries. |
| I-B2 | **Planner logic is not swappable / provider quirks hard-coded in gateway.** Retry rules, error classification, window behaviour are free functions in `gateway.py` (`_transient_retry_wait`, `_is_rate_limit`). | Code review 2026-11-10. |
| I-B3 | **Fast 500s with an empty window are never retried.** `chat_tool_retry_attempts=0`; 5xx never retried (ADR-0025). | Prod 2026-11-10 04:23:37 and 04:37:47: 500 after 1.2–1.3 s on call 1, minute window empty. User re-sent manually. Prod 2026-11-10 17:52:44: **inline** turn (3.6k tokens, no tools), benign prompt (Arabic, SN1/SN2 chemistry quiz), `MidStreamFallbackError` 500 after 1.19 s, before any text; user abandoned the session and started over. The inline path already has a "retry only before text reached the client" loop — only `_transient_retry_wait` refusing 5xx blocks it. |
| I-B4 | **Calls timed exactly at the window edge fail.** `try_reserve` waits until the oldest entry is `WINDOW_S` old (+0.05 s). Entries are stamped at reserve (call start); the provider likely counts later. With calls > half the limit, any skew overflows Google's cap → Google answers 500, not 429. | Prod 500s after waits ending at the edge: 2026-11-09 15:57:25, 16:01:13; 2026-11-10 04:24:38, 04:33:47, 04:39:48. |
| I-B5 | **A mid-turn failure loses the whole turn.** Turn persisted only on `complete` (`chat_service.chat_event_stream`); tool rounds already done (and their budget waits) are discarded. | 2026-11-10 04:33:47: 3 rounds, 181 s lost. 2026-11-09 15:57:25: 61 s lost. |
| I-B6 | **Failed turns are invisible to later turns.** Next turn has no idea what was read/attempted; model restarts or repeats. | 2026-11-10 lorebook session: the user had to repeat where to resume twice, then complained about repetition. |
| I-B7 | **Turn deadline ignores budget waits.** `final` is computed before `_acquire` waits, so a 150 s deadline turn ran 272 s. | Same lorebook turn. |
| I-B8 | **Failed calls keep their full reservation.** `_settle_failed` keeps the estimate even for a 1.2 s 500 that likely consumed nothing, so the user's retry waits for phantom usage. | 04:23:37 fast 500 → retry at 04:23:58 waited 38.7 s. |
| I-B9 | **Stale pacing config.** `deployments.yaml` assumes ~4k tokens/call ("~4 calls/min → 15 s"); real calls are 6–9.5k, so the token gate, not spacing, sets pace. | Settle logs 2026-11-09/10. |
| I-B10 | **History replays huge user messages verbatim.** 8 034-char first prompt replayed every turn; call 1 grew 5.6k → 8k tokens. | Lorebook session turn-plan logs. |
| I-B11 | **Provider safety blocks look like generic errors.** Content-filter outcomes (finish_reason SAFETY / blocked prompt) aren't distinguished from 500s. | Suspected for some content; not confirmed (see Open questions). |
| I-B12 | **Per-process budget is blind to other processes sharing the key.** | Possible: e2e host and prod may share the Google key. |
| I-B13 | **Long turns look frozen.** Budget waits (up to 64 s), paced retries after provider 500s and 3–5 tool rounds make a turn take 2–7 min; the UI shows one line ("Waiting for AI model capacity… ~51s" or the latest tool) with no plan, no step count and no reason for the wait. Users re-send or leave. | Live runs 2026-11-11: card turns 151–443 s, 31–82 `waiting` events; prod 2026-11-10 17:52 user abandoned after an error. **Tool steps are effectively invisible on budgeted deployments:** `SessionContext` keeps one `toolStatus` string and every `waiting` tick overwrites it; on Google each `tool` event is followed within milliseconds by the next round's pacing/token wait (15–51 s, ticks every 5 s), so the tool line shows for ~2 s per round (local check 2026-11-11). |

## Goals

- Plan the **whole turn** (rounds, waits, deadline) before the first call; tell the user the ETA.
- Provider-specific behaviour behind one interface, chosen per deployment.
- A transient provider failure costs one retry, not the turn.
- Failed turns are resumable and visible to later turns.

## Non-goals

- Surviving backend restarts: turn records/traces are **in-memory only** (session store). Lost on restart; accepted.
- Cross-process / Redis budget (I-B12) — documented as a deployment rule instead (B-90).
- An extra LLM call to "plan the plan". Rejected: costs ~5k tokens (≈40 % of a free-tier minute) and small models plan poorly; the server already knows exact field sizes. Planning is deterministic.

---

## 1. Module layout — `services/planning/` (new package)

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-01 | `services/planning/base.py`: `TurnPlanner` ABC with `plan(ctx: PlanContext) -> TurnPlan \| TooLarge \| JobProposal`. `PlanContext` = working JSON, message, history, deployment, litellm model, `BudgetSnapshot` (window usage now, limit, calibration ratio), intent (PRD C; `None` until then). | MVP | I-B2 |
| B-02 | `UnbudgetedPlanner` (no `tpm_input_limit`): today's size-based behaviour, unchanged. `BudgetedPlanner`: §2. Selected by `planner_for(deployment)` — by **budget type**, not provider. | MVP | I-B2 |
| B-03 | `turn_planner.py` becomes a thin shim re-exporting `plan_turn` → `planner_for(...).plan(...)` so callers (`chat_service.planner`) don't change in the first step. | MVP | I-B2 |
| B-04 | `TurnPlan` gains: `max_rounds` (now computed), `eta_s: float`, `est_turn_tokens: int`, `retry_reserve_tokens: int`. | MVP | I-B1 |

## 2. Whole-turn budget — `BudgetedPlanner`

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-10 | Estimate per-round cost: `round_k ≈ first_call + k × avg_tool_result_tokens`, where `avg_tool_result_tokens` = calibrated estimate of `min(chat_tool_result_max_chars, typical_read)`; `typical_read` from the doc (median serialised size of the array elements / largest string fields the skeleton exposes). | MVP | I-B1 |
| B-11 | `affordable_rounds` = largest `n ≤ chat_tool_max_rounds` such that `Σ round_0..n` (+ final-answer call) fits in `usable_per_min × turn_timeout_min − window_used_now`, where `usable_per_min = tpm_input_limit × headroom − safety_margin_tokens`. | MVP | I-B1 |
| B-12 | `affordable_rounds < 1` and mode would be skeleton → return `TooLarge` (existing `input_too_large` flow with sections) or, when PRD C intent = `review`, `JobProposal`. | MVP | I-B1 |
| B-13 | `eta_s` = simulated wall clock using the same window model as `deployment_budget` (pacing slot + token waits). Streamed once as SSE `plan` event: `{mode, max_rounds, eta_s}` before the first call. | MVP | I-B1 |
| B-14 | `retry_reserve_tokens` from the learned 5xx rate (B-28); included in B-11. | MVP | I-B3 |
| B-15 | Deadline (`chat_tool_turn_timeout_s`) is checked **after** `_acquire` returns as well as before; if the wait pushed past it, that round becomes the final round. `eta_s > turn_timeout` is impossible by B-11. | MVP | I-B7 |
| B-16 | Context compaction between rounds: tool results older than the last 2 rounds are replaced by `{"path", "chars", "summary": "<first 200 chars>"}` once the model has produced a later round. Planner estimates use the compacted size. | MVP | I-B1 |
| B-17 | Logging: INFO `turn plan mode=%s rounds=%d/%d est_turn_tokens=%d eta_s=%.0f window_used=%d`. | MVP | I-B1 |

## 3. Provider policy — `providers/policy.py`

Three layers, each with one job:

| Piece | When | Job |
|-------|------|-----|
| **Policy config** (`DeploymentPolicy`) | load time | fixed provider facts and safety caps, per deployment in `deployments.yaml` |
| **ProviderPolicy** | always | classifies errors, decides retries, learns recent provider behaviour |
| **Planner** | once per turn | turns policy values + live budget into rounds, retry reserve, ETA, mode |

```
planner  ──reads──▶ policy.snapshot()        (before the turn)
gateway  ──asks───▶ policy.classify / retry  (each error)
gateway  ──tells──▶ policy.record(outcome)   (each call)
```

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-19 | **`DeploymentPolicy`** (frozen dataclass, `deployment.policy`) loaded from a `policy:` block per deployment in `deployments.yaml`; every field falls back to the Settings default when omitted. Fields: `budget_headroom`, `window_margin_s`, `transient_fast_s`, `transient_retry_attempts`, `transient_retry_turn_max`, `transient_retry_wait_s`, `rate_limit_retry_attempts`, `rate_limit_retry_max_wait_s`. Google: today's tuned values; Ollama: no 5xx retries, margin 0. **Shipped in hotfix 2026-11-11.** | MVP | I-B2 |
| B-20 | `ProviderPolicy` ABC on each `DeploymentProvider`, built from its `DeploymentPolicy`; default impl = today's behaviour. Methods: `classify(exc, latency_s) -> ErrorKind`, `retry_decision(kind, call_attempt, turn_retries) -> wait_s \| None`, `failed_call_tokens(kind, estimate) -> int` (Google: full estimate, B-32), `record(outcome)`, `snapshot() -> PolicySnapshot`. Keyed per **deployment** (free vs paid tier differ). | MVP | I-B2 |
| B-21 | `ErrorKind`: `rate_limit`, `transient`, `safety_block`, `bad_request`, `fatal`. (`soft_rate_limit` dropped: with finish-time accounting, B-30, Google sent 0 × 429 in 4 live runs; remaining 500s were random, not load.) | MVP | I-B2, I-B11 |
| B-22 | Gateway (`_tool_loop`, single-call path) asks the policy instead of `_transient_retry_wait` / `_fast_transient` / `_is_rate_limit`; those helpers move into the default policy. | MVP | I-B2 |
| B-23 | `GoogleAIStudioPolicy.classify`: 5xx within `transient_fast_s` → `transient`; slow 5xx / timeout → `fatal`; 429 → `rate_limit`; blocked prompt / `finish_reason=SAFETY` → `safety_block`. | MVP | I-B3, I-B11 |
| B-24 | Retry rules: `transient` → up to `transient_retry_attempts` per call and `transient_retry_turn_max` per turn, wait `transient_retry_wait_s × n`; `rate_limit` → provider hint if ≤ `rate_limit_retry_max_wait_s`, up to `rate_limit_retry_attempts`; others → no retry. Retries go through `_acquire` (pacing slot + token gate; failed calls stay counted). Streamed calls retry only while no text has reached the client. Hotfix values (Google): 3 / 12 / 3 s — a live turn needed 7 retries (2026-11-11). | MVP | I-B3 |
| B-25 | Retry happens **per round** inside `_tool_loop`; completed rounds are kept. | MVP | I-B3, I-B5 |
| B-26 | `safety_block` → SSE `error` with `code="safety_block"` and a user-facing message ("The AI provider declined this request."), no stack/provider text. | MVP | I-B11 |
| B-27 | **Learned stats** (in memory, per deployment+model, EWMA over recent calls, bounded): `transient_rate` (5xx share; Google ≈ 0.4 on 2026-11-11), `avg_latency_s`, `avg_call_tokens`, plus the existing calibration ratio. Updated by `record(outcome)`; logged at INFO when they move > 20 %. | MVP | I-B1, I-B3 |
| B-28 | **Planner derives per turn** from `snapshot()`: expected attempts per call `= 1 / (1 − transient_rate)`; retry reserve `= (expected − 1) × round tokens` (tokens and time); `affordable_rounds` and `eta_s` include expected retries; mode choice (inline / skeleton+tools / `TooLarge` / `JobProposal`) uses the same numbers. Example: rate 0.4 → 1.67 attempts/round → under a 150 s turn timeout plan 2 rounds, not 4. Replaces the fixed B-14 reserve. | MVP | I-B1 |
| B-29 | **Learned values only make plans more cautious.** They never raise config caps (retry counts, headroom, limits); a worse `transient_rate` reduces planned rounds instead of adding retries. When the provider recovers, rates fall and rounds come back automatically. | MVP | I-B1, I-B3 |

## 4. Window accounting — `services/deployment_budget.py`

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-30 | Entries are reserved at send time and **re-stamped at finish** (success or failure) via `budget.finish()`, moved to the back so the window stays sorted. Live run 2026-11-11 (Google, 18–26 s calls): finish-time windows matched every accept/500/429 (13.2k OK, 15.3k OK, 17.3k → 500); send-time + margin did not. **Shipped in hotfix.** | MVP | I-B4 |
| B-31 | A call counts for `WINDOW_S + window_margin_s` after it **finishes**. `window_margin_s` per deployment in `deployments.yaml` (Google 4 s, default 0); later behind `policy.window_margin_s()`. **Shipped in hotfix.** | MVP | I-B4 |
| B-32 | Failed calls keep their full estimate, re-stamped at failure time. ~~Fast 500 → 0 tokens~~ disproved: live run 2026-11-11, a 3.8k call 429'd only because two failed fast-500 calls (~9.2k each) were still counted by Google. | MVP | I-B8 |
| B-33 | `BudgetSnapshot` accessor for the planner: `window_used`, `limit`, `ratio`, `next_slot_s`. Read-only. | MVP | I-B1 |
| B-34 | `min_call_interval_s` becomes optional/derived: when omitted on a budgeted deployment, spacing = `WINDOW_S × observed_avg_call_tokens / usable_per_min` (min 5 s). Update the stale `deployments.yaml` comment. | Later | I-B9 |

## 5. Turn records & resume — `services/chat_service.py`, `chat_history_service.py`

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-40 | Every turn is stored, not only completed ones. Assistant turn gains `status: "complete" \| "failed" \| "interrupted"` (default `complete`) and optional `error_code`. Quota-event turns stay unstored (ADR-0021 H-05 unchanged). | MVP | I-B5, I-B6 |
| B-41 | `trace` (server-only, in memory, never sent to the LLM verbatim): `{round_reached, messages_snapshot, tool_calls: [{name, args, result_chars}], json_hash, plan}`. `json_hash` = sha256 of compact working JSON at turn start. | MVP | I-B5 |
| B-42 | `POST /api/sessions/{id}/turns/{turnId}/resume` (SSE, same events as `/api/chat`): only for the **latest** turn with `status ∈ {failed, interrupted}`. If `json_hash` matches → continue the tool loop from `messages_snapshot` (rounds already done are not re-run). If not → stale rule B-44. | MVP | I-B5 |
| B-43 | On success the resumed turn's status becomes `complete` in place (no new user turn). Second resume of the same turn after success → 409. | MVP | I-B5 |
| B-44 | Stale rule: hash mismatch → drop tool results for paths whose value changed, keep the rest, re-plan from the remaining snapshot. If nothing reusable → resume acts like re-sending the original message. | MVP | I-B5 |
| B-45 | History replay (ADR-0021 C-01) includes failed/interrupted turns as a compact summary assistant message: `"(previous attempt failed: <error_code>; read: /entries/4, /entries/5, /entries/6)"`. Never the tool results themselves. | MVP | I-B6 |
| B-46 | Long user messages in history: user turns > `chat_history_user_max_chars` (default 1500) are replayed as head 1000 + `"…(N chars omitted)"` + tail 300, except the latest turn. | MVP | I-B10 |
| B-47 | A new `/api/chat` message while the latest turn is failed simply proceeds (resume is optional); the failed turn's trace is kept until the next turn completes, then dropped (memory bound). | MVP | I-B5 |

## 6. Settings (`settings.py`, pydantic Settings)

Settings hold **global** knobs and the **defaults** for `DeploymentPolicy` fields (B-19); provider-specific values live in `deployments.yaml` `policy:`.

| Stays global | Why |
|--------------|-----|
| `deployment_budget_max_wait_s` | how long a user waits is a UX choice |
| `chat_tool_turn_timeout_s`, `chat_tool_max_rounds` | turn shape, owned by the planner |
| history / quota / logging knobs | not provider behaviour |

| New field | Default |
|-----------|---------|
| `deployment_budget_safety_margin_tokens: int` | `1000` |
| `chat_history_user_max_chars: int` | `1500` |
| `chat_tool_keep_full_rounds: int` | `2` |

`chat_tool_retry_*` and `chat_transient_*` remain only as policy defaults.

## 8. Turn progress events — `gateway.py`, `services/progress.py` (new)

**Status: B-50…B-56 shipped (branch `feature/turn-progress`, 2026-11-11); B-57 later.** Live check on Google (card, typo prompt): plan, step X/N, cooldown/limit countdowns, retry lines and tool lines rendered through a 7-min turn with 9 provider 500s. Known gap: the plan ETA ("~2 min") ignores expected retries — fixed by B-28 learned 5xx rate.

Every long step tells the user what is happening and where the turn stands. **All messages are built in code** from the plan, tool name/args and the document (sizes, match counts): zero extra LLM tokens, deterministic, localisable later. Model-written status text was rejected: it costs tokens on a 16k/min budget, Google tool rounds are non-streaming (no live text), and it can be wrong.

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-50 | SSE `plan` (extends B-13), sent before the first call: `{mode, rounds_planned, calls_per_min, eta_s, message}`. `calls_per_min` from the policy/budget (Google free tier ≈ 1–4). Message e.g. *"Large document — planned up to 4 lookup steps; this model allows about 1 step per minute (~4 min)."* Inline mode: *"Sending your request to the AI model…"*. | MVP | I-B13 |
| B-51 | SSE `progress` `{stage, step, steps, message, detail?}` at every stage change. `stage ∈ {calling, tool, waiting, retrying, answering, applying}`; `step` = current round (1-based), `steps` = planned rounds + final answer. | MVP | I-B13 |
| B-52 | `calling`: *"Step 2/5 — asking the AI model"*. `answering` (final round): *"Step 5/5 — writing the answer"*. `applying`: *"Applying 6 changes…"* (after parse, before `diff` events). | MVP | I-B13 |
| B-53 | `tool` messages from `describe_tool_call(name, args, result, doc)`: *"Read /data/description (7,485 chars, part 1 of 2)"*, *"Searched values for 'timeout' — no matches"*, *"Queried /data/character_book/entries: 3 of 81 match"*. Uses the tool result (counts, truncation) — not just the args. Existing `tool` event keeps its fields and gains `message`. | MVP | I-B13 |
| B-54 | `waiting` gains `reason` and `step`: `pacing` → *"Spacing requests for this model's limit — next step in 12 s"*; `tokens` → *"This model's per-minute limit is used up — continuing in 45 s"*; `cooldown` (after a provider error, before the retry) → *"AI provider error — cooling down, retry 1/3 in 18 s"*. Ticks stay ≤ 5 s apart (existing). | MVP | I-B13 |
| B-55 | SSE `retrying` `{attempt, max, wait_s, kind}` when the policy retries (B-24): *"The AI provider had a temporary error — retrying (1/3)"*. Followed by `waiting(reason=cooldown)` if the pacing/token wait is longer than the backoff. | MVP | I-B13 |
| B-56 | Events are additive; clients that ignore them keep today's behaviour. Messages never include document values beyond paths, sizes and the user's own search terms (≤ 60 chars). | MVP | I-B13 |
| B-57 | Progress steps are recorded in the turn `trace` (B-41) as `[{t, stage, message}]` so a failed/resumed turn can show what already happened. | Later | I-B13, I-B5 |

## 7. Spec changes (`openapi/spec.yaml` first)

- SSE `plan` (B-50), `progress` (B-51), `retrying` (B-55); `waiting.reason`/`step` (B-54); `tool.message` (B-53).

- SSE `plan` event: `{mode, max_rounds, eta_s}`.
- SSE `error.code` enum gains `safety_block`, `provider_error`.
- `ChatTurn`: `status`, `error_code`.
- New endpoint `POST /api/sessions/{id}/turns/{turnId}/resume` (SSE; 404 unknown turn, 409 not resumable).

## Data flow (budgeted deployment)

```
/api/chat → planner_for(dep).plan(ctx: doc, msg, history, BudgetSnapshot)
          → TurnPlan{mode, max_rounds=affordable, eta_s}   ── SSE plan
          → gateway._tool_loop: per round
                _acquire (slot + window, margin) → call
                ok   → settle(actual, stamp=now) → trace.append
                err  → policy.classify → retry_decision → (retry round | fail)
          → complete  → turn status=complete
          → fail      → turn status=failed + trace  ── SSE error{code, turn_id, resumable}
/turns/{id}/resume → hash check → continue loop from trace
```

## Acceptance

- Lorebook replay (synthetic 876-entry doc, Google budget emulated on Ollama as in the 2026-11-10 repro): planner caps rounds so the turn ends ≤ `chat_tool_turn_timeout_s`; `plan` event ETA within ±30 % of actual.
- Injected fast 500 on round 2 → one retry, turn completes, rounds 1 not re-run.
- Injected failure on round 3 → turn stored `failed`; resume completes without re-running rounds 1–2.
- Next turn after a failed one sees the "previous attempt failed … read: …" summary in its messages.

## Tests

- Unit: planner math (rounds vs window usage), policy classification table, settle re-stamp + margin, failed-call token rules, resume (hash match / mismatch / 409), history summaries, user-message compaction.
- Live (`LIVE_LLM=1`, Ollama, budget emulated via fixture): synthetic large doc.

## Open questions

- **Fast 500s are random, not load (2026-11-11 replay):** one request, 12 calls 30 s apart, no other traffic → 5 × 500 + 1 timeout across variants. Hotfix: fast-5xx retries 3/call, 12/turn, no window condition (B-23's `soft_rate_limit` class may be unnecessary now that the budget matches Google's accounting).
- Live runs 2026-11-11 (Google, finish-time stamps): 0 Google 429s after the fix (3 before). Fast 500s remain: one on an empty window (retry succeeded — the prod 17:52 pattern), others at ~12.6–13k actual tokens/min (12.3k and 12.8k passed) and one on a final round with ~7.5k alone. Possibly prod traffic on the shared key. Decide after a separate-key test whether `deployment_budget_headroom` should drop to 0.75.
- Pacing fix shipped with the hotfix: a successful reservation pushes the next slot to `now + min_call_interval_s` (calls had gone out 2 s apart after a token wait).
- Are the fast 500s content-related or transient? 2026-11-10 17:52 fast 500 on a benign chemistry prompt points to **transient** (B-23 rule unchanged). Still confirm with a **separate test Google key** (not prod's): same synthetic doc, neutral vs sensitive-themed prompt, 10 runs each.
- ~~Does Google count input tokens of failed 500 calls?~~ Yes (live run 2026-11-11, see B-32).

## Deployment rule (instead of a shared budget)

| # | Requirement | Priority | Issue |
|---|-------------|----------|-------|
| B-90 | Each environment (prod, e2e, local) uses its **own** provider key; documented in `deployments.yaml` header and the compose/env docs. | MVP | I-B12 |

---

Related ADRs: 0016 (deployments), 0021 (history), 0024 (tools), 0025 (budget). New ADR: planner interface + provider policy + turn resume.
Turn records/traces: in-memory only.
