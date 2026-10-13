/** Chat-history helpers shared by SessionContext, ChatPanel, DiffViewer.
 *
 * The backend owns history and diff statuses; the client only renders and
 * mirrors them. Diffs from earlier turns can still be pending (the user kept
 * chatting without accepting/rejecting), so "pending" is collected across
 * every turn, not just the latest one.
 */

import type { ChatTurn, DiffEntry, DiffStatus } from './api';

/** Client-only turn: shown in the thread but never stored server-side
 *  (stream errored before the backend persisted it). Not mirrored. */
export type UiChatTurn = ChatTurn & { ephemeral?: boolean };

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
  const pairs = history
    .slice(start)
    .filter((t) => !t.ephemeral && t.kind !== 'boundary' && t.role === 'assistant').length;
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
