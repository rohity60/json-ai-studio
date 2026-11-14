/** Chat-history helpers shared by SessionContext, ChatPanel, DiffViewer.
 *
 * The backend owns history and diff statuses; the client only renders and
 * mirrors them. Diffs from earlier turns can still be pending (the user kept
 * chatting without accepting/rejecting), so "pending" is collected across
 * every turn, not just the latest one.
 */

import type { TurnProgress } from './progress';
import type { ChatTurn, DiffEntry, DiffStatus } from './api';

/** Client-only turn: shown in the thread but never stored server-side
 *  (stream errored before the backend persisted it). Not mirrored. */
// progress: client-only turn progress (lib/progress.ts), not stored by the server.
// resumeGone: the server can no longer continue this failed turn (404/409), so
// Continue is hidden (WB-07).
export type UiChatTurn = ChatTurn & { ephemeral?: boolean; progress?: TurnProgress; resumeGone?: boolean };

/** Failed or interrupted assistant turn (ADR-0028). */
export const isFailedTurn = (t: ChatTurn): boolean =>
  t.role === 'assistant' && (t.status === 'failed' || t.status === 'interrupted');

// Matches backend chat_history_max_turns (pairs replayed to the model).
export const MAX_CONTEXT_PAIRS = 10;

export const diffStatus = (d: DiffEntry): DiffStatus => d.status ?? 'pending';

export function pendingDiffs(history: UiChatTurn[]): DiffEntry[] {
  const out: DiffEntry[] = [];
  for (const turn of history) {
    for (const d of turn.diffs || []) {
      if (diffStatus(d) === 'pending') out.push(d);
    }
  }
  return out;
}

/** Number of user/assistant pairs the backend will replay (after the last
 *  boundary, capped). Mirrors ChatHistoryService._replayable_pairs. */
export function contextPairCount(history: UiChatTurn[]): number {
  let start = 0;
  history.forEach((t, i) => {
    if (t.kind === 'boundary') start = i + 1;
  });
  // A run of review-batch turns replays as ONE progress pair (ADR-0026).
  let pairs = 0;
  let inJobRun = false;
  for (const t of history.slice(start)) {
    if (t.ephemeral || t.kind === 'boundary') continue;
    if (t.kind === 'job_batch') {
      if (!inJobRun) pairs += 1;
      inJobRun = true;
      continue;
    }
    if (t.role === 'user') inJobRun = false;
    if (t.role === 'assistant') pairs += 1;
  }
  return Math.min(pairs, MAX_CONTEXT_PAIRS);
}

/** Copy diff statuses from the server's history onto the local thread.
 *  Keeps local-only (ephemeral) turns intact instead of replacing the list. */
export function syncStatuses(local: UiChatTurn[], server?: ChatTurn[] | null): UiChatTurn[] {
  if (!server) return local;
  const byId = new Map<string, DiffEntry>();
  for (const turn of server) for (const d of turn.diffs || []) byId.set(d.id, d);
  return local.map((turn) =>
    turn.diffs?.length
      ? {
          ...turn,
          diffs: turn.diffs.map((d) => {
            const s = byId.get(d.id);
            return s ? { ...d, status: s.status, failure_reason: s.failure_reason } : d;
          }),
        }
      : turn,
  );
}
