// Drop-in replacement for apps/web/src/lib/api.ts inside the Anna App.
//
// The web app's SessionContext and components are reused unchanged; the
// build swaps their `lib/api` import for this module (see vite.config.ts).
// Same function names, arguments and return shapes — but each call goes to
// the Executa through the Anna host instead of HTTP. `apiKey` arguments are
// accepted and ignored: the Anna host identifies the user.

import { invoke, invokeJob } from './runtime';

export type { ChatTurn, DiffEntry, DiffStatus } from '../../../../web/src/lib/api';

export async function createSession(name: string, _apiKey?: string) {
  return invoke('create_session', { name });
}

export async function getSession(sessionId: string, _apiKey?: string) {
  return invoke('get_doc', { session_id: sessionId });
}

export async function restoreVersions(sessionId: string, payload: Record<string, any>, _apiKey?: string) {
  return invoke('restore_versions', { session_id: sessionId, payload });
}

export async function createVersion(
  sessionId: string, label: string, workingJson: Record<string, any>, _apiKey?: string,
) {
  return invoke('save_version', { session_id: sessionId, label, json: workingJson });
}

export async function uploadJson(
  jsonBody: string | null, _file: File | undefined, _apiKey?: string, sessionId?: string,
) {
  return invoke('upload_json', { json: jsonBody ?? '{}', session_id: sessionId });
}

export async function acceptDiff(sessionId: string, diffId: string, _apiKey?: string) {
  return invoke('accept_diff', { session_id: sessionId, diff_id: diffId });
}

export async function rejectDiff(sessionId: string, diffId: string, _apiKey?: string) {
  return invoke('reject_diff', { session_id: sessionId, diff_id: diffId });
}

export async function acceptDiffBatch(sessionId: string, _apiKey?: string) {
  return invoke('accept_all', { session_id: sessionId });
}

export async function rejectDiffBatch(sessionId: string, _apiKey?: string) {
  return invoke('reject_all', { session_id: sessionId });
}

export async function getVersions(sessionId: string, _apiKey?: string) {
  return invoke('list_versions', { session_id: sessionId });
}

export async function selectVersion(sessionId: string, versionId: string, _apiKey?: string) {
  return invoke('select_version', { session_id: sessionId, version_id: versionId });
}

export async function clearChat(sessionId: string, _apiKey?: string): Promise<void> {
  await invoke('clear_chat', { session_id: sessionId });
}

export async function explain(
  sessionId: string, _workingJson: Record<string, any>, _apiKey?: string,
): Promise<string> {
  const out = await invoke<{ markdown: string }>('explain', { session_id: sessionId });
  return out.markdown;
}

/** No accounts inside Anna: the Anna user is the user. */
export async function getMe(): Promise<Record<string, any> | null> {
  return null;
}

/** One chat turn as the same `{type, data}` chunks the web SSE stream
 *  yields. Progress chunks arrive live from the async job; `diff` and
 *  `complete` come with its result. */
export async function* streamChat(
  sessionId: string,
  message: string,
  _workingJson: object | null,
  _apiKey?: string,
  thinking: boolean = false,
  focusPath?: string,
) {
  const args: Record<string, any> = { session_id: sessionId, message, thinking };
  if (focusPath) args.focus_path = focusPath;

  const live = new Set<string>(); // event types already yielded as progress
  for await (const update of invokeJob('chat_turn', args)) {
    if (update.kind === 'progress') {
      const { event, data } = update.data ?? {};
      if (!event) continue;
      live.add(event);
      yield { type: event as string, data };
      continue;
    }
    for (const item of update.data?.events ?? []) {
      const isOutcome = item.event === 'diff' || item.event === 'complete';
      if (!isOutcome && live.has(item.event)) continue; // already shown live
      if (item.event === 'complete' && item.data?.working_json_omitted) {
        // Too large for a job result: fetch the document separately.
        const session = await getSession(sessionId);
        item.data.working_json = session.working_json;
        item.data.baseline_json = session.baseline_json;
      }
      yield { type: item.event as string, data: item.data };
    }
  }
}

export async function listDocs(): Promise<Array<{ id: string; name?: string; updated_at?: string }>> {
  const out = await invoke<{ docs: any[] }>('list_docs');
  return out.docs ?? [];
}
