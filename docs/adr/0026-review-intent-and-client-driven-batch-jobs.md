# 0026-review-intent-and-client-driven-batch-jobs

**Date**: 2026-11-13
**Status**: Proposed

## Context

Users ask the chat to review or repair a **whole** large document ("review and fix every entry", "look for errors" on a card with ~90k chars of text, a lorebook with ~900 entries). Before this ADR such a message went into the lookup-tool loop (ADR-0024) like any point edit:

- Each tool round resends the earlier results, so on a small per-minute budget (Google free tier: 16k input tokens/min, ~12.8k usable, ADR-0025) only ~20k chars of the document were read per turn, about one record per round.
- Nothing told the user the job could not fit; the model improvised "capability" speeches or asked them to type "continue".
- Users asked for exactly this: batched, resumable progress without babysitting.

## Decision

1. **Deterministic intent rules, no model call** (`services/intent.py`). `classify_intent(message, doc_stats)` → `point_edit | bulk_edit | review | question` from en/pt/es keyword rules. `review` needs a whole-document or whole-collection scope signal; a named single target stays `point_edit`; unknown → `point_edit` (unchanged behaviour). Each result carries a rule id for the logs. Rules cost zero tokens and cannot fail; a misroute falls back to today's behaviour.

2. **Proposal before spending** (`services/review_proposal.py`). A `review` that does not fit one inline turn is not sent to the model. `/api/chat` emits SSE `job_proposal` (`scope_path`, `record_count`, `batch_count`, `est_tokens`, `eta_s`, `instruction`) and a `complete` that states the numbers; the turn is stored with `kind="job_proposal"`.

3. **One packer for estimate and run** (`services/job_packing.py`). Batch size is never a fixed record count. Room per batch, in tokens of records:

   `min(per-minute budget − prompt overhead − retry reserve, context window − prompt overhead, llm_max_tokens × job_input_per_output)`

   and records are packed greedily from the cursor by their own calibrated token size (`deployment_budget.calibrated`). A record larger than the room is walked leaf by leaf; long strings go in pages cut at whitespace, and the cursor holds a sub-position inside the record. The proposal simulates a full run with the same function.

4. **Lean batch prompt.** Instruction + output contract (`replace_text` preferred, ADR-0024 text edits) + that batch's records with their JSON Pointer paths. No skeleton, no chat history, no tools — the prompt stays flat however large the document is, and the per-minute overhead is paid once per batch.

5. **The client drives the job** (`services/job_service.py`, `controllers/jobs.py`). `POST /jobs` creates; each `POST /jobs/{id}/next` processes **exactly one batch** over SSE; `GET` reads; `DELETE` cancels and leaves the diffs pending. There is no server worker: closing the tab pauses, and the web app restores an unfinished job **paused**. Job state lives in the session dict (in memory) and is lost on a backend restart, like sessions themselves (ADR-0006/0013).

6. **Batches are ordinary gateway calls.** `/next` calls `GatewayService.invoke` with a planner callback that packs the batch, so it shares the deployment budget, pacing, retries, usage and credit/quota checks with chat (ADR-0015, ADR-0025) without gateway changes. A quota event ends the batch without moving the cursor; a provider failure marks the job `failed` and the next `/next` retries the same batch; an unreadable (cut-off) answer is retried with half the room.

7. **Diffs stay ordinary.** Batch diffs are pending diffs tagged `job_id` / `batch_no`, pass the truncation guard and the failed-diff path, and changes outside the batch's records are refused. `accept-all` / `reject-all` take `job_id` and `batch_no`. Each batch appends one `job_batch` history turn; the model sees only the latest as a single progress line.

8. **Chat alongside a job.** While a batch is in flight, non-question chat messages get 409 `job_running`; questions are answered. Between batches edits are allowed and unprocessed records are reviewed with their current value. The web loop does not start a batch while a chat turn of the same tab is streaming, so a question is not queued behind a full-window batch.

## Consequences

- Large reviews run at roughly one full-budget batch per minute window on the free tier (dozens of records per call instead of ~one), with a cost shown up front.
- One active job per session; upload and version switch cancel it.
- Restart loses running jobs (accepted); the client shows the job as gone.
- A question asked while a job runs still shares the per-minute budget and may wait up to one window.
- `chat_history_max_stored_turns` also bounds how many batch turns (and their pending diffs) a session keeps.
- Intent rules are keyword lists; new languages or phrasings need new rules. Unknown stays `point_edit`.

## Alternatives considered

- **Server background worker.** Survives a closed tab, but needs job persistence, cancellation across processes and quota attribution without a request; out of scope for an in-memory store.
- **LLM intent classification.** One extra call per message on a 16k/min budget, and nondeterministic routing.
- **Fixed records per batch.** Wrong on every deployment but one: too big for the free tier, wasteful on large-context models.
- **Bigger tool loop.** Each round resends earlier results; cost grows quadratically with what is read.

## References

- PRD C: `apps/api/ai/feature/large-doc-review/requirements.md`, `apps/web/ai/feature/large-doc-review/requirements.md`
- ADR-0015 (quotas), ADR-0021 (history), ADR-0022 (bulk), ADR-0024 (tools, text edits), ADR-0025 (budget, planner)
