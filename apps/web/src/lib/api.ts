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

export async function* streamChat(sessionId: string, message: string, workingJson: object | null, apiKey: string) {
    console.log('[api] streamChat ENTRY: sessionId=', sessionId.slice(0, 8), 'msgLen=', message.length, 'wjKeys=', workingJson ? Object.keys(workingJson).length : 'null');

    const formData = new FormData();
    formData.append('session_id', sessionId);
    formData.append('message', message);
    if (workingJson) {
        formData.append('working_json_str', JSON.stringify(workingJson));
    }

    console.log('[api] streamChat POSTING to /api/chat...');
    const fetchStart = performance.now();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000); // 2 min timeout to prevent infinite hangs
    try {
        const res = await fetch(`${BASE}/chat`, {method: 'POST', headers: {'X-API-Key': apiKey}, body: formData, signal: controller.signal});
        console.log('[api] streamChat fetch response: status=' + res.status, 'elapsedMs=' + (performance.now() - fetchStart).toFixed(0));
        if (!res.ok) throw new Error(`Chat failed: ${await res.text()}`);

        const reader = res.body!.getReader();
        console.log('[api] streamChat SSE reader acquired');
        const decoder = new TextDecoder();
        let chunkIndex = 0;
        let buffer = ''; // Accumulates raw decoded text chunk by chunk
        let eventTypeCache: string | null = null; // State tracker for the current event type
        console.log('[api] streamChat SSE reader acquired');

        while (true) {
            chunkIndex++
            console.log('[api] streamChat calling reader.read() #cycle=' + chunkIndex);
            const startTimeMs = performance.now();
            const {done, value} = await reader.read();
            const elapsed = performance.now() - startTimeMs;
            console.log('[api] streamChat reader.read() returned: done=' + done + ' bytes=' + (value ? value.length : 0) + ' cycleElapsedMs=' + elapsed.toFixed(0));
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
               // Process the entire accumulated buffer for complete SSE chunks
            let currentBuffer = buffer;
            buffer = ''; // Clear buffer for next read cycle

               // Splits by \n\n or handles last line if it's not followed by a blank line
            const potentialChunks = currentBuffer.split(/\r?\n\r?\n/);

            for (const chunk of potentialChunks) {
                if (!chunk) continue;

                let lines = chunk.split('\n'); // Split the single chunk into raw lines
                let tempEventType: string | null = null;
                let dataLines: string[] = [];

                   // Process line-by-line within this complete SSE message block
                for (const line of lines) {
                    const trimmedLine = line.trim();
                    if (!trimmedLine) continue;

                    if (trimmedLine.startsWith('event: ')) {
                        tempEventType = trimmedLine.substring(7).trim();
                        dataLines = []; // Reset data payload on new event start
                        continue;
                       } else if (trimmedLine.startsWith('data')) {
                        let dataPayload = trimmedLine.substring(4).trim();
                           // Handle continuation lines (if payload starts with 'data:' but follows another 'data:')
                        dataLines.push(dataPayload);
                       }
                   }

                if (!tempEventType) continue; // Must have an event type to yield anything

                const combinedData = dataLines.join('\n');
                let eventType = tempEventType;
                let rawData = combinedData.trim();

                   // Attempt JSON parse for final payload
                try {
                    const dataObject = JSON.parse(rawData);
                    console.log('[api] streamChat yield chunk (parsed): type=' + eventType + ' keys=' + Object.keys(dataObject).join(','));
                    yield {type: eventType, data: dataObject};

                   } catch (e) {
                       // Fallback: Treat as raw text payload
                    console.log('[api] streamChat yield chunk (raw): type=' + eventType);
                    yield {type: eventType, data: {text: rawData}};
                   }

               }
           } // End while(true) loop

           // Final error handling remains outside the streaming logic
        } catch (err: any) {
            clearTimeout(timeoutId);
            if (err.name === 'AbortError') {
                throw new Error('LLM request timed out. Server may be slow or unavailable.');
              }
            console.error('[api] streamChat error in fetch/reader:', err?.message || String(err));
            throw err;
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
