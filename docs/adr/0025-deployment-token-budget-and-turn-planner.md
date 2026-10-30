# 0025-deployment-token-budget-and-turn-planner

**Date**: 2026-10-30
**Status**: Proposed

## Context

Prod (2026-10-28) failed chat turns on `google_ai_studio` / `gemma-4-26b-a4b-it` with provider 429s: `generate_content_free_tier_input_token_count, limit: 16000` — 16k **input tokens per minute per model**, shared by every anonymous user behind one key.

- **Inline cutoff ignores the provider budget.** `LLM_MAX_INLINE_CHARS` (120k chars ≈ 44k tokens) decides inline vs skeleton globally. Any document between ~35k and 120k chars is inlined and can never fit Google's free tier, while larger documents (skeleton + tools, ADR-0024) do fit.
- **One turn is several calls.** A skeleton turn runs up to `CHAT_TOOL_MAX_ROUNDS` (4) rounds, each resending system prompt, skeleton, history (≤ `CHAT_HISTORY_MAX_TOKENS`) and earlier tool results. A ~5k-token prompt can send 20k+ tokens in one minute by itself.
- **Requests share the minute.** At 03:17:46 a turn was rejected in 387 ms ("retry in 13s") because the previous turn had used the window. No per-request size check prevents that.
- **The user sees the wrong message.** Every provider failure becomes `service_unavailable` ("flaky behavior due to high load", retry 30 s). For an oversized document, retrying never helps.
- Per-user caps (`credit_service`: per-minute tokens + monthly credits, keyed by `quota_key`, ADR-0015) answer a different question — what one caller may use — and know nothing about provider limits.

## Decision

1. **Per-deployment input budget in `deployments.yaml`.** New optional keys:
   - `tpm_input_limit` — provider input tokens per minute per model (Google free: `16000`). Unset = no deployment budget.
   - `context_tokens` — model context window, when LiteLLM does not know it.
   Budgets apply per deployment **and model** (Google's quota dimension is the model).

2. **Token estimates come from the real prompt.** The planner builds the actual `messages` (system prompt, format notes, history replay, inline doc or skeleton, user message) and counts them with `litellm.token_counter`. Because Gemma's tokenizer is unknown to LiteLLM, each deployment+model keeps a **calibration ratio** (moving average of provider `usage.prompt_tokens` ÷ our estimate) applied to every later estimate. Tool rounds add a per-round allowance (`CHAT_TOOL_RESULT_MAX_CHARS` + tool-call text). Headroom: plan against 80 % of the limit.

3. **Turn planner** (before the first LLM call) keeps the two views from before (full JSON or skeleton + tools); the budget only moves the line between them. It picks the first whose **first call** fits `min(context − reserve_output, deployment per-minute limit × headroom)`; later tool rounds are budgeted one at a time by the counter (6):

   | View | Model sees | User's document |
   |---|---|---|
   | Inline | full document, 1 call | unchanged |
   | Skeleton + tools | key-union skeleton (ADR-0024); all `CHAT_TOOL_MAX_ROUNDS` allowed | unchanged; diffs and bulk ops (ADR-0022) apply to the full doc |
   | Too large | nothing sent | `input_too_large` event with options |

   No third "first N items" view: a partial sample of a heterogeneous array hides keys and `$type`s that the key-union skeleton shows, and two views keep the model's instructions unambiguous. `LLM_MAX_INLINE_CHARS` stays as an upper cap; the planner can only choose a smaller prompt than today, never a larger one.

4. **Trimmer** (`json_trim.py`), only for the user's trimmed copy in `input_too_large` — never for what the model sees. Keeps the shape; arrays cut to the first *k* items, strings capped (300 → 120 → 60 chars), object keys capped as a last resort; binary search on *k* for the largest copy that fits. Cut report aggregated by path pattern (`/records: 1240 → 25 items`, `/records/*/text: 18 values capped at 300 chars`).

5. **Section focus** (lossless fallback). Optional `focus_path` on `ChatRequest`: the model sees and edits only that subtree; diff paths are prefixed back onto the full document. `input_too_large` lists candidate paths that fit, so the UI can offer them without another call.

6. **Deployment budget counter** (`services/deployment_budget.py`), separate from `credit_service`:
   - Sliding 60 s window of input tokens keyed by deployment + model; in-memory. Check-and-append never awaits, so it is atomic on the event loop and concurrent turns cannot both claim the last headroom.
   - Per LLM call (each tool round is a call): `reserve(estimate)` → call → `settle(actual_prompt_tokens)` on success (also updates calibration) or `release()` on failure.
   - A provider 429 marks the window full until its `retryDelay` elapses (parser already in `gateway.py`).
   - No headroom: **wait** for the window — first call or any later tool round — up to `DEPLOYMENT_BUDGET_MAX_WAIT_S` (60 s, one window), streaming a `waiting` event every ≤5 s with the remaining seconds; then continue. The model is never told to cut a turn short for budget reasons. Only a wait beyond that (e.g. a provider 429 with a 2-minute hint) ends the turn with `rate_limit`, `scope: "model"`, real `retry_after`. Either way the provider is not called while the window is full, so it does not 429.
   - Not implemented: failing over to another enabled deployment with headroom (only one deployment is enabled in prod).

7. **Independence from per-user caps.**
   - Order: `credit_service.check(principal)` → planner → `deployment_budget.reserve()` per call → `credit_service.deduct()` with actual usage (unchanged).
   - A deployment wait or rejection never deducts credits or adds to the user's token window — nothing was sent.
   - Separate keys and storage; changing one limit never affects the other.
   - Distinct events: user cap → `scope: "user"`, `login_available` per ADR-0015; deployment → `scope: "model"`, `login_available: false` (logging in does not raise provider capacity).

8. **No token numbers in the UI.** Estimated vs actual tokens, drift and calibration go to logs and usage records only. Events carry what the user can act on: `retry_after` seconds, document size in **KB** (token limit converted back via the calibrated chars-per-token ratio), and the cut report. Credits remain the only quota unit shown.

9. **Honest provider-429 handling.** A 429 that still reaches the provider (limit misconfigured, key shared with another app) becomes `rate_limit` (`scope: "model"`, provider `retryDelay`) instead of `service_unavailable`. `service_unavailable` is kept for real outages.

10. **Global call pacing.** Optional `min_call_interval_s` per deployment (Google free tier: 15 s ≈ 16k ÷ ~4k tokens per skeleton call). Every LLM call — any user, any turn, every tool round — claims the next slot (`claim_slot`, key = deployment + model) and waits for it with the `waiting` countdown before the token reservation. Bursts are spread over the minute instead of hitting the cap at once. A slot further away than `DEPLOYMENT_BUDGET_MAX_WAIT_S` ends the turn with a model-scope `rate_limit`. Rounds stay per turn (`CHAT_TOOL_MAX_ROUNDS`); the budget and the pacing are global.
11. **No retries; failed calls stay counted.** `CHAT_TOOL_RETRY_ATTEMPTS` defaults to 0: a failed LLM call (5xx or 429) ends the turn with `service_unavailable` / model-scope `rate_limit`. Google's free tier answers 500 in bursts and sometimes on a first call after an idle minute (live test 2026-10-30); every retry added to its per-minute count, and pacing plus the token gate (at limit × headroom) keep load down instead. If the knob is raised, only a 429 with a short provider hint (≤ `CHAT_TOOL_RETRY_MAX_WAIT_S`) is retried, before any text reached the client; 5xx never are. A failed call keeps its reservation at the estimate. Google tool rounds run non-streaming (`tool_streaming: false`): streamed rounds failed mid-stream on most first attempts. Replaces ADR-0024 §6 (per-round retries).

## Consequences

- Mid-size documents on Google free tier (roughly 35–120k chars) move from guaranteed failure (inlined, ~44k tokens) to skeleton + tools.
- On Google free tier each skeleton call resends ~3.8k tokens, so about 3 calls fit per minute (typical tool results are 40–530 tokens). A 4-round turn therefore spans more than one window: later rounds wait (countdown shown) instead of 429-ing mid-turn as before (ADR-0024). Turns get slower, not shorter.
- With 15 s pacing a turn with N LLM calls takes at least 15 × (N − 1) s (a 4-lookup turn ≥ 60 s), more when other users queue. Waits count toward `CHAT_TOOL_TURN_TIMEOUT_S` (150 s); past it the tool loop's existing forced final answer still applies.
- The frontend's chat stream timeout is an idle timeout (2 min without events), re-armed on every chunk, so long waits are not aborted.
- **Single-process only.** Counters live in one process, like the existing rate limiter. With N uvicorn workers each would allow the full limit — needs a shared store (Redis) or the limit divided by N before scaling out.
- Calibration starts at 1.0 after each restart; the 80 % headroom covers the first calls.
- Frontend: `waiting` shows as the chat status line; model-scope `rate_limit` opens an "AI model at capacity" popup without login CTA; `input_too_large` opens `TooLargeModal` (edit a section → resend with `focus_path`; download trimmed copy). Opening the trimmed copy as a new session was left out: switching sessions would hide the user's full document.
- **Out of scope:** credits are cost-based and Gemma on AI Studio is priced `(0.0, 0.0)`, so prod chats charge 0 credits and monthly caps never trigger. Tracked separately.

## References

- ADR-0007 (fail-fast), ADR-0015 (auth & quotas), ADR-0016 (deployment registry), ADR-0021 (history budget), ADR-0022 (bulk edits), ADR-0024 (lookup tools; documents the 16k/min cap)
- Code: `gateway.py` (`invoke`, `_tool_loop`, `_transient_retry_wait`), `prompting.py` (`is_skeleton_mode`), `services/chat_history_service.py` (`fit_to_context`), `services/credit_service.py`
- Prod log: 2026-10-28 03:17, session `45f0337075e74506ab3d604698f9bfab`
