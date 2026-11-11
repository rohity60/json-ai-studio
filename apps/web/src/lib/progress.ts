// Turn progress shown inside the pending assistant bubble (PRD B §8,
// web WB-08..12). Built from the server's plan / progress / tool / waiting /
// retrying SSE events; client-side only (not stored with the turn yet).

export type ProgressLine = { kind: 'tool' | 'retry'; text: string };

export type TurnProgress = {
  plan: string | null; // "Large document — the AI will look things up in up to 5 steps…"
  step: number | null;
  steps: number | null;
  current: string | null; // "Step 2/5 — asking the AI model"
  wait: { message: string; reason: string; until: number } | null;
  done: ProgressLine[]; // finished lookups and retries, oldest first
  startedAt: number;
  finishedAt: number | null;
  structured: boolean; // server sent plan/progress events (new backend)
};

export function newProgress(now: number = Date.now()): TurnProgress {
  return {
    plan: null,
    step: null,
    steps: null,
    current: null,
    wait: null,
    done: [],
    startedAt: now,
    finishedAt: null,
    structured: false,
  };
}

// Fallback for servers that send `tool` without a message.
export function describeToolCall(name: string, rawArgs?: string): string {
  let args: Record<string, any> = {};
  try { args = JSON.parse(rawArgs || '{}'); } catch { /* truncated args */ }
  if (name === 'search') return `Searched the document for “${args.query ?? '…'}”`;
  if (name === 'read') return `Read ${args.path || 'the document'}`;
  if (name === 'query') return `Queried ${args.path || 'the document'}`;
  return `Looked up ${name}`;
}

/** Fold one SSE event into the progress; null when it is not a progress event. */
export function applyProgressEvent(
  p: TurnProgress,
  type: string,
  data: any,
  now: number = Date.now(),
): TurnProgress | null {
  switch (type) {
    case 'plan':
      return {
        ...p,
        structured: true,
        plan: typeof data?.message === 'string' ? data.message : p.plan,
        steps: typeof data?.steps === 'number' ? data.steps : p.steps,
      };
    case 'progress':
      return {
        ...p,
        structured: true,
        current: data?.message ?? p.current,
        step: typeof data?.step === 'number' ? data.step : p.step,
        steps: typeof data?.steps === 'number' ? data.steps : p.steps,
        wait: null,
      };
    case 'tool':
      if (!data?.name) return null;
      return {
        ...p,
        done: [...p.done, { kind: 'tool', text: data.message || describeToolCall(data.name, data.args) }],
        current: null,
        wait: null,
      };
    case 'waiting': {
      const seconds = Number(data?.retry_after) || 0;
      // A wait between steps belongs to the NEXT step (server sends it).
      const nextStep = typeof data?.step === 'number' ? data.step : p.step;
      return {
        ...p,
        step: nextStep,
        current: nextStep !== p.step ? null : p.current,
        wait: {
          message: data?.message || 'Waiting for AI model capacity…',
          reason: data?.reason || 'tokens',
          until: now + seconds * 1000,
        },
      };
    }
    case 'retrying':
      return {
        ...p,
        structured: true,
        done: [...p.done, { kind: 'retry', text: data?.message || 'Retrying after a temporary AI provider error' }],
        wait: null,
      };
    default:
      return null;
  }
}

/** Plain text for the bubble when the server sends no structured events
 *  (older backend): last tool step + current wait, as before. */
export function legacyProgressText(p: TurnProgress): string {
  const lastTool = [...p.done].reverse().find((l) => l.kind === 'tool')?.text ?? '';
  if (!p.wait) return lastTool;
  const secs = Math.max(0, Math.ceil((p.wait.until - Date.now()) / 1000));
  return [lastTool && `✓ ${lastTool}`, `Waiting for AI model capacity… ~${secs}s`]
    .filter(Boolean)
    .join('\n');
}

export function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return rest ? `${m} min ${rest} s` : `${m} min`;
}
