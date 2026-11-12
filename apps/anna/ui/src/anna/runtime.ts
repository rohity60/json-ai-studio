// Bridge to the Anna host and the JSON AI Studio Executa.
//
// The host serves its SDK at a fixed URL inside the app iframe; it is not
// an npm dependency of the bundle, so it is loaded at runtime.

const SDK_URL = '/static/anna-apps/_sdk/latest/index.js';
export const TOOL_ID = 'tool-json-ai-studio-json-ai-studio-nk262zbg';

// Sync tool calls may run up to 90 s on the host.
const SYNC_TIMEOUT_MS = 90_000;
const JOB_POLL_MS = 400;

let anna: any = null;

export async function connect(): Promise<any> {
  if (anna) return anna;
  const sdk = await import(/* @vite-ignore */ SDK_URL);
  anna = await sdk.AnnaAppRuntime.connect();
  return anna;
}

export function host(): any {
  if (!anna) throw new Error('Anna runtime is not connected');
  return anna;
}

/** Error shaped like the web client's HTTP errors (`status`), so the shared
 *  session code keeps its 404 / 409 handling. The Executa prefixes those
 *  two cases: "404: Session not found". */
function toolError(raw: any): Error {
  const message = String(raw?.message ?? raw ?? 'Request failed');
  const match = /^(\d{3}): (.*)$/s.exec(message);
  const err: any = new Error(match ? match[2] : message);
  if (match) err.status = Number(match[1]);
  err.code = raw?.code;
  return err;
}

/** The host unwraps `{success, data}`; tolerate either shape. */
function unwrap(result: any): any {
  if (result && typeof result === 'object' && 'success' in result) {
    if (result.success === false) throw toolError(result.error);
    return result.data;
  }
  return result;
}

export async function invoke<T = any>(method: string, args: Record<string, any> = {}): Promise<T> {
  try {
    const out = await host().tools.invoke({
      tool_id: TOOL_ID,
      method,
      args,
      timeoutMs: SYNC_TIMEOUT_MS,
    });
    return unwrap(out) as T;
  } catch (err: any) {
    throw err?.status ? err : toolError(err);
  }
}

export type JobUpdate =
  | { kind: 'progress'; data: any }
  | { kind: 'result'; data: any };

/** Run a tool as an async job: yields its progress events as they arrive,
 *  then its result. Used for chat turns, which can outlast a sync call. */
export async function* invokeJob(
  method: string,
  args: Record<string, any>,
): AsyncGenerator<JobUpdate> {
  const tools = host().tools;
  let job: any;
  try {
    job = await tools.invokeAsync({ tool_id: TOOL_ID, method, args });
  } catch (err: any) {
    throw toolError(err);
  }
  let seen = 0;
  for (;;) {
    const view = await tools.getJob({ jobId: job.jobId });
    for (const item of view.progress ?? []) {
      if (item.seq <= seen) continue;
      seen = item.seq;
      if (item.type === 'progress' || item.type === 'tool_update') {
        yield { kind: 'progress', data: item.data };
      }
    }
    if (view.state === 'succeeded') {
      yield { kind: 'result', data: unwrap(view.result) };
      return;
    }
    if (view.state !== 'queued' && view.state !== 'running') {
      throw toolError(view.error ?? `The request ${view.state}. Please try again.`);
    }
    await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
  }
}
