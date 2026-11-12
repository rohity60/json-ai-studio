'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Hourglass, ListChecks, Loader2, Pause, Play, RotateCw, X } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import Button from '@/components/ui/Button';
import { pendingDiffs } from '@/lib/chatHistory';
import { formatDuration } from '@/lib/progress';

/** Whole-document review job (ADR-0026, WC-03/05/06): progress, the current
 *  wait, ETA, and Pause / Resume / Cancel / Retry batch. The job only
 *  advances while this tab keeps asking for batches. */
export default function JobPanel() {
  const { state, pauseJob, resumeJob, cancelJob, dismissJob } = useSession();
  const ui = state.job;
  const waiting = !!ui?.wait;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!waiting) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [waiting]);

  if (!ui) return null;
  const { job, phase } = ui;
  const pct = job.total ? Math.min(100, Math.round((job.cursor / job.total) * 100)) : 0;
  const pending = pendingDiffs(state.conversationHistory).filter((d) => d.job_id === job.id).length;
  const batches = job.batch_count ? `${job.batches_done} of ~${job.batch_count}` : `${job.batches_done}`;
  const secs = ui.wait ? Math.max(0, Math.ceil((ui.wait.until - now) / 1000)) : 0;
  const finished = phase === 'done' || phase === 'cancelled';

  const title =
    phase === 'done' ? 'Review complete'
      : phase === 'cancelled' ? 'Review cancelled'
        : phase === 'failed' ? 'Review stopped — a batch failed'
          : phase === 'paused' ? 'Review paused'
            : ui.pausing ? 'Pausing after this batch…'
              : 'Reviewing in batches';

  return (
    <div className="border-t bg-purple-50/60 px-4 py-3 text-xs" data-testid="job-panel" aria-live="polite">
      <div className="flex items-center gap-1.5 font-semibold text-purple-900">
        {phase === 'done' ? <CheckCircle2 className="w-3.5 h-3.5 text-green-600" />
          : phase === 'failed' ? <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
            : <ListChecks className="w-3.5 h-3.5" />}
        <span>{title}</span>
        <span className="ml-auto font-normal text-gray-600" data-testid="job-progress">
          {job.cursor.toLocaleString()} / {job.total.toLocaleString()} items
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-purple-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-full transition-all ${phase === 'failed' ? 'bg-red-400' : 'bg-purple-600'}`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-gray-700">
        <span>Batches: {batches}</span>
        <span data-testid="job-pending">Pending changes: {pending.toLocaleString()}</span>
        {!finished && job.eta_s != null && job.eta_s > 0 && (
          <span>About {formatDuration(job.eta_s * 1000)} left</span>
        )}
      </div>

      {ui.wait && phase === 'running' && (
        <div className={`mt-1.5 flex items-center gap-1.5 ${ui.wait.reason === 'cooldown' ? 'text-amber-700' : 'text-gray-600'}`}>
          <Hourglass className="w-3 h-3 shrink-0" />
          <span>{ui.wait.message} · {secs}s</span>
        </div>
      )}
      {!ui.wait && ui.current && phase === 'running' && (
        <div className="mt-1.5 flex items-center gap-1.5 text-gray-600">
          <Loader2 className="w-3 h-3 shrink-0 animate-spin" />
          <span>{ui.current}</span>
        </div>
      )}
      {ui.error && phase !== 'running' && (
        <p className="mt-1.5 text-red-700 break-words" data-testid="job-error">{ui.error}</p>
      )}
      {phase === 'paused' && !ui.error && (
        <p className="mt-1.5 text-gray-600">Nothing runs while paused. Resume to continue from item {job.cursor + 1}.</p>
      )}
      {phase === 'failed' && !ui.retryable && (
        <p className="mt-1.5 text-gray-600">This batch cannot be retried. Cancel the review, or change the content and start again.</p>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {phase === 'running' && (
          <Button variant="secondary" onClick={pauseJob} disabled={ui.pausing}>
            <Pause className="w-3.5 h-3.5" /> Pause
          </Button>
        )}
        {phase === 'paused' && (
          <Button variant="primary" onClick={resumeJob}>
            <Play className="w-3.5 h-3.5" /> Resume
          </Button>
        )}
        {phase === 'failed' && ui.retryable && (
          <Button variant="primary" onClick={resumeJob}>
            <RotateCw className="w-3.5 h-3.5" /> Retry batch
          </Button>
        )}
        {!finished && (
          <Button variant="ghost" onClick={cancelJob} disabled={ui.pausing && phase === 'running'}>
            <X className="w-3.5 h-3.5" /> Cancel
          </Button>
        )}
        {finished && (
          <Button variant="ghost" onClick={dismissJob}>
            <X className="w-3.5 h-3.5" /> Close
          </Button>
        )}
      </div>
    </div>
  );
}
