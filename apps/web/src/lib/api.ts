/** API client helpers for the JSON AI Studio backend. */

// In dev: NEXT_PUBLIC_API_BASE=http://localhost:8000/api
// In prod: /api (relative, served by reverse proxy like nginx)
const BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

export async function createSession(name: string, apiKey: string) {
    console.log('[api] createSession ENTRY, name:', name);
    const res = await fetch(`${BASE}/sessions`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({name}),
    });
    if (!res.ok) throw new Error(`Failed to create session: ${await res.text()}`);
    console.log('[api] createSession OK, status:', res.status);
    return await res.json();
}

export async function getSession(sessionId: string, apiKey: string) {
    console.log('[api] getSession ENTRY, sessionId:', sessionId.slice(0, 8));
    const res = await fetch(`${BASE}/sessions/${sessionId}`, {
        headers: {'X-API-Key': apiKey},
    });
    if (!res.ok) throw new Error('Failed to load session');
    console.log('[api] getSession OK, status:', res.status);
    return await res.json();
}

export async function createVersion(
    sessionId: string, label: string, workingJson: Record<string, any>, apiKey: string,
) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({label, json_data: workingJson}),
    });
    if (!res.ok) throw new Error('Failed to create version');
    return await res.json();
}

export async function uploadJson(
    jsonBody: string | null, _file: File | undefined, apiKey: string, sessionId?: string,
) {
    console.log('[api] uploadJson ENTRY, hasBody=', !!jsonBody, 'sessionId:', sessionId);
    const formData = new FormData();
    if (_file) formData.append('file', _file);
    if (jsonBody) formData.append('json_body', jsonBody);
    if (sessionId) formData.append('session_id', sessionId);

    const res = await fetch(`${BASE}/json/upload`, {method: 'POST', headers: {'X-API-Key': apiKey}, body: formData});
    if (!res.ok) throw new Error(`Upload failed: ${await res.text()}`);
    console.log('[api] uploadJson OK, status:', res.status);
    return await res.json();
}

export async function validateJson(jsonData: object, apiKey: string) {
    const res = await fetch(`${BASE}/validate`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({json_data: jsonData}),
    });
    if (!res.ok) throw new Error('Validation failed');
    return await res.json();
}

export async function computeDiff(oldJson: object, newJson: object, apiKey: string) {
    const res = await fetch(`${BASE}/diff`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({old_json: oldJson, new_json: newJson}),
    });
    if (!res.ok) throw new Error('Diff computation failed');
    return await res.json();
}

export async function acceptDiff(sessionId: string, diffId: string, apiKey: string) {
    console.log('[api] acceptDiff ENTRY, sessionId:', sessionId.slice(0, 8), 'diffId:', diffId);
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/${diffId}/accept`, {
        method: 'POST',
        headers: {'X-API-Key': apiKey},
    });
    if (!res.ok) throw new Error('Failed to accept diff');
    console.log('[api] acceptDiff OK, status:', res.status);
    return await res.json();
}

export async function rejectDiff(sessionId: string, diffId: string, apiKey: string) {
    console.log('[api] rejectDiff ENTRY, sessionId:', sessionId.slice(0, 8), 'diffId:', diffId);
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/${diffId}/reject`, {
        method: 'POST',
        headers: {'X-API-Key': apiKey},
    });
    if (!res.ok) throw new Error('Failed to reject diff');
    console.log('[api] rejectDiff OK, status:', res.status);
    return await res.json();
}

export async function exportSession(sessionId: string, format = 'pretty', apiKey: string) {
    const url = `${BASE}/sessions/${sessionId}/export?format=${format}`;
    const res = await fetch(url, {headers: {'X-API-Key': apiKey}});
    if (!res.ok) throw new Error('Export failed');
    return await res.blob();
}

export async function getVersions(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/versions`, {
        headers: {'X-API-Key': apiKey},
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
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({ versionId }),
      });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `Failed to select version: ${res.status}`);
       }
    return await res.json();
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
    console.log('[api] streamChat ENTRY: sessionId=', sessionId.slice(0, 8), 'msgLen=', message.length, 'wjKeys=', workingJson ? Object.keys(workingJson).length : 'null');

    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('message', message);
    if (workingJson) {
        formData.append('working_json_str', JSON.stringify(workingJson));
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000); // 2 min timeout to prevent infinite hangs
    try {
        const res = await fetch(`${BASE}/chat`, {method: 'POST', headers: {'X-API-Key': apiKey}, body: formData, signal: controller.signal});
        if (!res.ok) throw new Error(`Chat failed: ${await res.text()}`);

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
        console.error('[api] streamChat error in fetch/reader:', err?.message || String(err));
        throw err;
    } finally {
        clearTimeout(timeoutId);
    }
}

export async function acceptDiffBatch(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/accept-all`, {
        method: 'POST',
        headers: {'X-API-Key': apiKey},
    });
    if (!res.ok) throw new Error('Failed to accept all diffs');
    return await res.json();
}

export async function rejectDiffBatch(sessionId: string, apiKey: string) {
    const res = await fetch(`${BASE}/sessions/${sessionId}/diffs/reject-all`, {
        method: 'POST',
        headers: {'X-API-Key': apiKey},
    });
    if (!res.ok) throw new Error('Failed to reject all diffs');
    return await res.json();
}

export async function explain(
    sessionId: string,
    workingJson: Record<string, any>,
    apiKey: string,
): Promise<string> {
    const res = await fetch(`${BASE}/explain`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
        body: JSON.stringify({sessionId, workingJson}),
       });
    if (!res.ok) throw new Error(`Explain failed: ${await res.text()}`);
    return await res.text();
}
