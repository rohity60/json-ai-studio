/** IndexedDB workspace mirror (ADR-0014).
 *
 * Persists version snapshots + working JSON in the browser so they survive
 * backend restarts (the backend session store is in-memory). One record
 * under a fixed key: version ids (v1, v2, ...) collide across sessions, so
 * a single atomic workspace snapshot is safer than per-version records and
 * survives sessionId churn by design.
 *
 * Every function degrades to a no-op on failure (private browsing, storage
 * pressure, missing IndexedDB) — the cache must never break the app.
 */

import { openDB, type IDBPDatabase } from 'idb';

const DB_NAME = 'json-ai-studio';
const DB_VERSION = 1;
const STORE = 'workspace';
const KEY = 'current';

export type CachedVersionSnapshot = {
    id: string;
    parent_id: string | null;
    json_data: Record<string, any>;
    label: string;
    created_at: string;
};

export type CachedWorkspace = {
    sessionId: string | null;
    versions: CachedVersionSnapshot[];
    workingJson: Record<string, any>;
    baselineJson: Record<string, any>;
    activeVersionId: string | null;
    updatedAt: string;
};

function available(): boolean {
    return typeof indexedDB !== 'undefined';
}

async function getDb(): Promise<IDBPDatabase> {
    return openDB(DB_NAME, DB_VERSION, {
        upgrade(db) {
            if (!db.objectStoreNames.contains(STORE)) {
                db.createObjectStore(STORE);
            }
        },
    });
}

export async function saveWorkspace(ws: CachedWorkspace): Promise<void> {
    if (!available()) return;
    try {
        const db = await getDb();
        await db.put(STORE, ws, KEY);
    } catch (err) {
        console.warn('[versionCache] saveWorkspace failed:', err);
    }
}

export async function loadWorkspace(): Promise<CachedWorkspace | null> {
    if (!available()) return null;
    try {
        const db = await getDb();
        const ws = await db.get(STORE, KEY);
        return (ws as CachedWorkspace) ?? null;
    } catch (err) {
        console.warn('[versionCache] loadWorkspace failed:', err);
        return null;
    }
}

export async function clearWorkspace(): Promise<void> {
    if (!available()) return;
    try {
        const db = await getDb();
        await db.delete(STORE, KEY);
    } catch (err) {
        console.warn('[versionCache] clearWorkspace failed:', err);
    }
}
