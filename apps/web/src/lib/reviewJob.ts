// Client state of a whole-document review job (ADR-0026, WC-02..WC-06).
// The client drives the job: it asks the server for one batch at a time, so
// "running" here means "the loop in SessionContext keeps requesting batches".

import type { Job } from './api';

export type JobPhase = 'running' | 'paused' | 'failed' | 'done' | 'cancelled';

export type JobUi = {
  job: Job; // last server snapshot
  phase: JobPhase;
  inFlight: boolean; // a /next stream is open right now
  pausing: boolean; // pause/cancel asked; the open batch finishes first
  current: string | null; // "Asking the AI model…"
  wait: { message: string; reason: string; until: number } | null;
  error: string | null;
  retryable: boolean;
};

/** Phase for a job loaded from the server (page load, refocus): never
 *  auto-run — an unfinished job comes back paused (WC-06). */
export function phaseOf(job: Job): JobPhase {
  if (job.status === 'done') return 'done';
  if (job.status === 'cancelled') return 'cancelled';
  if (job.status === 'failed') return 'failed';
  return 'paused';
}

export function newJobUi(job: Job, phase: JobPhase = phaseOf(job)): JobUi {
  return {
    job,
    phase,
    inFlight: false,
    pausing: false,
    current: null,
    wait: null,
    error: job.status === 'failed' ? job.error ?? 'The last batch failed.' : null,
    retryable: true,
  };
}

export const isActivePhase = (phase: JobPhase) =>
  phase === 'running' || phase === 'paused' || phase === 'failed';

/** "items 25–36" for a batch's 0-based inclusive range. */
export function rangeLabel(start: number, end: number): string {
  return start === end ? `item ${start + 1}` : `items ${start + 1}–${end + 1}`;
}
