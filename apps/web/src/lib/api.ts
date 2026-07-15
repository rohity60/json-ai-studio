/** API client helpers for the JSON AI Studio backend. */

import { getBearerToken } from './authToken';

// In dev: NEXT_PUBLIC_API_BASE=http://localhost:8000/api
// In prod: /api (relative, served by reverse proxy like nginx)
const BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

/** Auth headers for every backend call: logged-in users send the Auth0
 *  bearer token (per-user quota); anonymous users send X-API-Key against
 *  the shared free pool (ADR-0015). */
async function authHeaders(
    apiKey: string,
    extra: Record<string, string> = {},
): Promise<Record<string, string>> {
    const token = await getBearerToken();
    return token
        ? {...extra, Authorization: `Bearer ${token}`}
        : {...extra, 'X-API-Key': apiKey};
}

/** Build an Error from a non-OK response, carrying the HTTP status, the
 *  Retry-After hint (seconds), and the parsed JSON detail (loginAvailable)
 *  so callers can detect 402/429 quota errors and show the popup. */
async function httpError(res: Response, prefix: string): Promise<Error> {
    const body = await res.text().catch(() => '');
    const err: any = new Error(`${prefix}: ${body || res.status}`);
    err.status = res.status;
    const retryAfter = res.headers.get('Retry-After');
    if (retryAfter) err.retryAfter = Number(retryAfter);
    try {
        const parsed = JSON.parse(body);
        const detail = parsed?.detail ?? parsed;
        err.detail = detail;
        if (detail && typeof detail === 'object') {
            err.loginAvailable = detail.login_available === true;
            if (err.retryAfter == null && detail.retry_after != null) {
                err.retryAfter = Number(detail.retry_after);
            }
        }
    } catch {
        // non-JSON body — keep the raw text message
    }
    return err;
}

export async function createSession(name: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({name}),
    });
    if (!res.ok) throw await httpError(res, 'Failed to create session');
    return await res.json();
}

export async function getSession(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}`, {
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) {
        // Carry the HTTP status: 404 (session gone → restorable from cache)
        // must be distinguishable from network/5xx (backend down → retry later)
        const err: any = new Error(`Failed to load session: ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return await res.json();
}

export async function restoreVersions(
    sessionId: string,
    payload: {
        versions: Array<{
            id: string;
            parent_id: string | null;
            json_data: Record<string, any>;
            label: string;
            created_at: string;
        }>;
        working_json?: Record<string, any>;
        baseline_json?: Record<string, any>;
        active_version_id?: string | null;
    },
    apiKey: string,
) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions/restore`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Failed to restore versions: ${await res.text()}`);
    return await res.json();
}

export async function createVersion(
    sessionId: string, label: string, workingJson: Record<string, any>, apiKey: string,
) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({label, json_data: workingJson}),
    });
    if (!res.ok) throw new Error('Failed to create version');
    return await res.json();
}

export async function uploadJson(
    jsonBody: string | null, _file: File | undefined, apiKey: string, sessionId?: string,
) {
    const formData = new FormData();
    if (_file) formData.append('file', _file);
    if (jsonBody) formData.append('json_body', jsonBody);
    if (sessionId) formData.append('session_id', sessionId);

    const res = await fetch(`${BASE}/json/upload`, {
        method: 'POST',
        headers: await authHeaders(apiKey),
        body: formData,
    });
    if (!res.ok) throw await httpError(res, 'Upload failed');
    return await res.json();
}

export async function validateJson(jsonData: object, apiKey: string) {
    const res = await fetch(`${BASE}/validate`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({json_data: jsonData}),
    });
    if (!res.ok) throw new Error('Validation failed');
    return await res.json();
}

export async function computeDiff(oldJson: object, newJson: object, apiKey: string) {
    const res = await fetch(`${BASE}/diff`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({old_json: oldJson, new_json: newJson}),
    });
    if (!res.ok) throw new Error('Diff computation failed');
    return await res.json();
}

export async function acceptDiff(sessionId: string, diffId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/${diffId}/accept`, {
        method: 'POST',
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) throw new Error('Failed to accept diff');
    return await res.json();
}

export async function rejectDiff(sessionId: string, diffId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/${diffId}/reject`, {
        method: 'POST',
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) throw new Error('Failed to reject diff');
    return await res.json();
}

export async function exportSession(sessionId: string, format = 'pretty', apiKey: string) {
    const url = `${BASE}/sessions/${sessionId}/export?format=${format}`;
    const res = await fetch(url, {headers: await authHeaders(apiKey)});
    if (!res.ok) throw new Error('Export failed');
    return await res.blob();
}

export async function getVersions(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions`, {
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) throw new Error('Failed to fetch versions');
    return await res.json();
}

export async function selectVersion(
    sessionId: string,
    versionId: string,
    apiKey: string,
): Promise<{
    working_json: Record<string, any>;
    baseline_json: Record<string, any>;
    active_version_id: string | null;
    versions: any[];
    conversation_history: any[];
}> {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions/select`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({ versionId }),
      });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `Failed to select version: ${res.status}`);
       }
    return await res.json();
}

/** Fetch the logged-in user's profile + credit quota. Returns null when
 *  anonymous (no bearer token) or when the backend has no user DB. */
export async function getMe(): Promise<Record<string, any> | null> {
    const token = await getBearerToken();
    if (!token) return null;
    const res = await fetch(`${BASE}/me`, {
        headers: {Authorization: `Bearer ${token}`},
    });
    if (!res.ok) return null;
    return await res.json();
}

// -- Workspaces (ADR-0018) — bearer-only persistence layer -----------------

export type WorkspaceSummary = {
    id: string;
    name: string;
    is_default: boolean;
    document_count: number;
    updated_at: string;
};

export type JsonDocumentSummary = {
    id: string;
    tag: string;
    version_count: number;
    latest_version_number: number;
    updated_at: string;
};

export type WorkspaceJsonVersion = {
    id: string;
    version_number: number;
    label: string | null;
    content: Record<string, any>;
    created_at: string;
};

export type JsonDocumentDetail = {
    id: string;
    tag: string;
    versions: WorkspaceJsonVersion[]; // ordered by version_number ascending
};

export type NewVersionPayload = {
    label: string | null;
    content: Record<string, any>;
};

/** Bearer-only headers: workspace routes must never fall back to X-API-Key.
 *  Missing token throws the same 401/loginAvailable shape httpError builds,
 *  so callers funnel into the login CTA without a network round-trip. */
async function workspaceHeaders(
    extra: Record<string, string> = {},
): Promise<Record<string, string>> {
    const token = await getBearerToken();
    if (!token) {
        const err: any = new Error('Login required to use workspaces.');
        err.status = 401;
        err.loginAvailable = true;
        throw err;
    }
    return {...extra, Authorization: `Bearer ${token}`};
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
    const res = await fetch(`${BASE}/workspaces`, {
        headers: await workspaceHeaders(),
    });
    if (!res.ok) throw await httpError(res, 'Failed to list workspaces');
    return await res.json();
}

export async function createWorkspace(name: string): Promise<WorkspaceSummary> {
    const res = await fetch(`${BASE}/workspaces`, {
        method: 'POST',
        headers: await workspaceHeaders({'Content-Type': 'application/json'}),
        body: JSON.stringify({name}),
    });
    if (!res.ok) throw await httpError(res, 'Failed to create workspace');
    return await res.json();
}

export async function renameWorkspace(
    workspaceId: string,
    name: string,
): Promise<WorkspaceSummary> {
    const res = await fetch(`${BASE}/workspaces/${workspaceId}`, {
        method: 'PATCH',
        headers: await workspaceHeaders({'Content-Type': 'application/json'}),
        body: JSON.stringify({name}),
    });
    if (!res.ok) throw await httpError(res, 'Failed to rename workspace');
    return await res.json();
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
    const res = await fetch(`${BASE}/workspaces/${workspaceId}`, {
        method: 'DELETE',
        headers: await workspaceHeaders(),
    });
    if (!res.ok) throw await httpError(res, 'Failed to delete workspace');
}

export async function listWorkspaceJsons(
    workspaceId: string,
): Promise<JsonDocumentSummary[]> {
    const res = await fetch(`${BASE}/workspaces/${workspaceId}/jsons`, {
        headers: await workspaceHeaders(),
    });
    if (!res.ok) throw await httpError(res, 'Failed to list JSONs');
    return await res.json();
}

export async function saveWorkspaceJson(
    workspaceId: string,
    payload: {tag: string; versions: NewVersionPayload[]},
): Promise<JsonDocumentSummary> {
    const res = await fetch(`${BASE}/workspaces/${workspaceId}/jsons`, {
        method: 'POST',
        headers: await workspaceHeaders({'Content-Type': 'application/json'}),
        body: JSON.stringify(payload),
    });
    if (!res.ok) throw await httpError(res, 'Failed to save JSON');
    return await res.json();
}

export async function getWorkspaceJson(
    workspaceId: string,
    documentId: string,
): Promise<JsonDocumentDetail> {
    const res = await fetch(
        `${BASE}/workspaces/${workspaceId}/jsons/${documentId}`,
        {headers: await workspaceHeaders()},
    );
    if (!res.ok) throw await httpError(res, 'Failed to load JSON');
    return await res.json();
}

export async function renameWorkspaceJson(
    workspaceId: string,
    documentId: string,
    tag: string,
): Promise<JsonDocumentSummary> {
    const res = await fetch(
        `${BASE}/workspaces/${workspaceId}/jsons/${documentId}`,
        {
            method: 'PATCH',
            headers: await workspaceHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify({tag}),
        },
    );
    if (!res.ok) throw await httpError(res, 'Failed to rename JSON');
    return await res.json();
}

export async function deleteWorkspaceJson(
    workspaceId: string,
    documentId: string,
): Promise<void> {
    const res = await fetch(
        `${BASE}/workspaces/${workspaceId}/jsons/${documentId}`,
        {method: 'DELETE', headers: await workspaceHeaders()},
    );
    if (!res.ok) throw await httpError(res, 'Failed to delete JSON');
}

export async function appendJsonVersions(
    workspaceId: string,
    documentId: string,
    payload: {versions: NewVersionPayload[]},
): Promise<WorkspaceJsonVersion[]> {
    const res = await fetch(
        `${BASE}/workspaces/${workspaceId}/jsons/${documentId}/versions`,
        {
            method: 'POST',
            headers: await workspaceHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify(payload),
        },
    );
    if (!res.ok) throw await httpError(res, 'Failed to save versions');
    return await res.json();
}

export async function deleteJsonVersion(
    workspaceId: string,
    documentId: string,
    versionId: string,
): Promise<void> {
    const res = await fetch(
        `${BASE}/workspaces/${workspaceId}/jsons/${documentId}/versions/${versionId}`,
        {method: 'DELETE', headers: await workspaceHeaders()},
    );
    if (!res.ok) throw await httpError(res, 'Failed to delete version');
}

/** Parse one complete SSE event block into {type, data}, or null.
 *  Tolerates both "data: {...}" (spec) and legacy "data{...}" payload lines. */
function parseSseBlock(block: string): {type: string; data: any} | null {
    let eventType: string | null = null;
    const dataLines: string[] = [];

    for (const line of block.split('\n')) {
        const trimmedLine = line.trim();
        if (!trimmedLine) continue;

        if (trimmedLine.startsWith('event:')) {
            eventType = trimmedLine.substring(6).trim();
            dataLines.length = 0; // reset payload on new event start
        } else if (trimmedLine.startsWith('data')) {
            // Strip "data:", "data: ", or bare "data" prefix
            dataLines.push(trimmedLine.replace(/^data:?\s?/, ''));
        }
    }

    if (!eventType) return null;

    const rawData = dataLines.join('\n').trim();
    try {
        return {type: eventType, data: JSON.parse(rawData)};
    } catch {
        // Fallback: treat as raw text payload
        return {type: eventType, data: {text: rawData}};
    }
}

export async function* streamChat(sessionId: string, message: string, workingJson: object | null, apiKey: string) {

    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('message', message);
    if (workingJson) {
        formData.append('working_json_str', JSON.stringify(workingJson));
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000); // 2 min timeout to prevent infinite hangs
    try {
        const res = await fetch(`${BASE}/chat`, {
            method: 'POST',
            headers: await authHeaders(apiKey),
            body: formData,
            signal: controller.signal,
        });
        if (!res.ok) throw await httpError(res, 'Chat failed');

        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = ''; // Accumulates raw decoded text across reads

        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                buffer += decoder.decode(); // flush decoder state
                break;
            }
            buffer += decoder.decode(value, {stream: true});

            // Split on blank lines; the last element may be an incomplete
            // event still arriving, so keep it in the buffer for the next read.
            const blocks = buffer.split(/\r?\n\r?\n/);
            buffer = blocks.pop() ?? '';

            for (const block of blocks) {
                if (!block.trim()) continue;
                const parsed = parseSseBlock(block);
                if (parsed) yield parsed;
            }
        }

        // Emit any final event that wasn't followed by a trailing blank line
        if (buffer.trim()) {
            const parsed = parseSseBlock(buffer);
            if (parsed) yield parsed;
        }
    } catch (err: any) {
        if (err.name === 'AbortError') {
            throw new Error('LLM request timed out. Server may be slow or unavailable.');
        }
        throw err;
    } finally {
        clearTimeout(timeoutId);
    }
}

export async function acceptDiffBatch(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/accept-all`, {
        method: 'POST',
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) throw new Error('Failed to accept all diffs');
    return await res.json();
}

export async function rejectDiffBatch(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/reject-all`, {
        method: 'POST',
        headers: await authHeaders(apiKey),
    });
    if (!res.ok) throw new Error('Failed to reject all diffs');
    return await res.json();
}

/** Seed a new session from a static template (Open in Workspace, ADR-0020).
 *  Free (no LLM call). Works anonymously (X-API-Key) or logged-in (bearer). */
export async function seedFromTemplate(
    templateSlug: string,
    templateTitle: string,
    json: unknown,
    starterPrompts: string[],
    apiKey: string,
): Promise<{
    id: string;
    name: string;
    working_json: Record<string, any>;
    starter_prompts: string[];
}> {
    const res = await fetch(`${BASE}/sessions/from-template`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({templateSlug, templateTitle, json, starterPrompts}),
    });
    if (!res.ok) throw await httpError(res, 'Open in Workspace failed');
    return await res.json();
}

export async function explain(
    sessionId: string,
    workingJson: Record<string, any>,
    apiKey: string,
): Promise<string> {
    const res = await fetch(`${BASE}/explain`, {
        method: 'POST',
        headers: await authHeaders(apiKey, {'Content-Type': 'application/json'}),
        body: JSON.stringify({sessionId, workingJson}),
       });
    if (!res.ok) throw await httpError(res, 'Explain failed');
    return await res.text();
}
