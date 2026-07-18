'use client';

/**
 * Workspace persistence layer (ADR-0018). Owns everything workspace:
 * list, active workspace/document, dirty tracking, load/save mappings.
 * Nests INSIDE SessionProvider (needs useSession for load/save); the
 * session runtime itself stays untouched.
 *
 * Dirty tracking: `savedVersionIds` are SESSION version ids already
 * persisted (on load, DB ids are reused as session ids by the restore
 * seam, so the bookkeeping is a plain set intersection). Work is dirty
 * only when the working JSON matches NONE of the persisted versions'
 * content — selecting any already-saved version stays clean.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useUser } from '@auth0/nextjs-auth0';
import { toast } from 'sonner';
import * as api from '../lib/api';
import type { JsonDocumentSummary, WorkspaceSummary } from '../lib/api';
import { useSession } from './SessionContext';
import { showRateLimitModal } from '@/components/RateLimitModal';
import { showSaveDialog } from '@/components/SaveDialog';

const WS_STORAGE_KEY = 'json-ai-studio-workspace';

// Client-side mirror of the server limits (server 409s stay authoritative).
export const WORKSPACE_LIMITS = { maxJsons: 5, maxVersions: 5 };

// Key-order-insensitive serialization: Postgres JSONB does not preserve key
// order, so byte comparison against DB content needs a canonical form.
function canonicalJson(v: any): string {
  if (Array.isArray(v)) return '[' + v.map(canonicalJson).join(',') + ']';
  if (v && typeof v === 'object') {
    return (
      '{' +
      Object.keys(v)
        .sort()
        .map((k) => JSON.stringify(k) + ':' + canonicalJson(v[k]))
        .join(',') +
      '}'
    );
  }
  return JSON.stringify(v);
}

export type SaveInput = {
  workspaceId?: string; // existing workspace…
  newWorkspaceName?: string; // …or create one on the fly
  documentId?: string; // append into existing document…
  tag?: string; // …or save as a new document with this tag
};

type WorkspaceContextValue = {
  workspaces: WorkspaceSummary[];
  activeWorkspaceId: string | null;
  documents: JsonDocumentSummary[];
  activeDocumentId: string | null;
  limits: typeof WORKSPACE_LIMITS;
  loadingWorkspaces: boolean;
  loadingDocuments: boolean;
  loggedIn: boolean;
  dirty: boolean;
  /** A save is in flight (drives the "Saving…" status). */
  saving: boolean;
  /** Header status pill: signed-out, in-flight, pending edits, or safe. */
  status: 'local' | 'saving' | 'unsaved' | 'saved';
  /** One-click save into the active document; opens the dialog only when
   *  there is no active document yet (a first save needs a tag). */
  saveActive: () => Promise<boolean>;
  /** Pending session versions + working-copy delta the next save would persist. */
  pendingSave: { versions: Array<{ label: string; content: Record<string, any> }>; workingChanged: boolean };
  /** ALL session versions + working-copy delta, ignoring the dirty baseline.
   *  Payload for "save as new JSON" (a copy) — pendingSave would be empty
   *  once everything was saved to some other document. */
  fullSave: { versions: Array<{ label: string; content: Record<string, any> }>; workingChanged: boolean };
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<WorkspaceSummary>;
  renameWorkspace: (id: string, name: string) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  selectWorkspace: (id: string) => Promise<void>;
  /** Load a document into the session, optionally at a specific version
   *  (defaults to latest). Resolves true when it actually loaded. */
  loadDocument: (docId: string, targetVersionId?: string) => Promise<boolean>;
  saveWork: (input: SaveInput) => Promise<void>;
  deleteDocument: (docId: string) => Promise<void>;
  deleteVersion: (docId: string, versionId: string) => Promise<void>;
  /** True = proceed (clean, saved, or discarded); false = user cancelled. */
  guardDirty: () => Promise<boolean>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

/** Shared error funnel: 401 → login CTA, 429 → rate-limit modal, 503 →
 *  unavailable. Returns true when handled. Never clears loaded workspace
 *  state — a transient failure must not lose what's already on screen. */
function handleWorkspaceError(err: any): boolean {
  if (err?.status === 401) {
    showRateLimitModal({ scope: 'api', kind: 'login' });
    return true;
  }
  if (err?.status === 429) {
    showRateLimitModal({ scope: 'api', kind: 'rate', retryAfter: err.retryAfter });
    return true;
  }
  if (err?.status === 503) {
    toast.error('Workspaces are temporarily unavailable.');
    return true;
  }
  return false;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { state: session, loadSnapshot, clearSession } = useSession();
  // Login state comes from the Auth0 session cookie — the SAME source as
  // UserChip — not from /api/me: that call is quota-rate-limited, and a
  // transient 429 must not downgrade the workspace UI to anonymous while
  // the header still shows the user as logged in.
  const { user } = useUser();
  const loggedIn = !!user;

  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<JsonDocumentSummary[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [saving, setSaving] = useState(false);
  // saveActive/guardDirty are defined before saveWork; call it through a ref
  // to avoid a declaration-order cycle.
  const saveWorkRef = useRef<(input: SaveInput) => Promise<void>>(async () => {});

  // Dirty baseline (state, not refs — dirty must recompute on change).
  // Session version ids already persisted for the loaded document.
  const [savedVersionIds, setSavedVersionIds] = useState<Set<string>>(new Set());

  const persistSelection = (wsId: string | null, docId: string | null) => {
    localStorage.setItem(
      WS_STORAGE_KEY,
      JSON.stringify({ workspaceId: wsId, documentId: docId }),
    );
  };

  const pendingSave = useMemo(() => {
    const versions = session.versions
      .filter((v) => !savedVersionIds.has(v.id))
      .map((v) => ({ label: v.label, content: v.json_data as Record<string, any> }));
    const empty = Object.keys(session.workingJson ?? {}).length === 0;
    // Contents already persisted for the loaded document. Working JSON equal
    // to any of them (e.g. after selecting an OLDER saved version) is clean —
    // dirty must not fire just because it differs from the version we opened.
    const persistedContents = new Set(
      session.versions
        .filter((v) => savedVersionIds.has(v.id))
        .map((v) => canonicalJson(v.json_data)),
    );
    const workingChanged =
      !empty && !persistedContents.has(canonicalJson(session.workingJson));
    return { versions, workingChanged };
  }, [session.versions, session.workingJson, savedVersionIds]);

  const fullSave = useMemo(() => {
    const versions = session.versions.map((v) => ({
      label: v.label,
      content: v.json_data as Record<string, any>,
    }));
    const empty = Object.keys(session.workingJson ?? {}).length === 0;
    // Copy semantics: only add a working-copy version when it differs from
    // every session version being written.
    const allContents = new Set(session.versions.map((v) => canonicalJson(v.json_data)));
    const workingChanged = !empty && !allContents.has(canonicalJson(session.workingJson));
    return { versions, workingChanged };
  }, [session.versions, session.workingJson]);

  // Anonymous flow never guards — nothing can be persisted anyway (F8).
  const dirty = loggedIn && (pendingSave.versions.length > 0 || pendingSave.workingChanged);

  // Header status: signed-out work is local-only; otherwise reflect whether a
  // save is running / pending / done. Persistence is a state you can SEE.
  const status: 'local' | 'saving' | 'unsaved' | 'saved' = !loggedIn
    ? 'local'
    : saving
      ? 'saving'
      : dirty
        ? 'unsaved'
        : 'saved';

  const markClean = useCallback((persistedSessionIds: string[]) => {
    setSavedVersionIds((prev) => {
      const next = new Set(prev);
      for (const id of persistedSessionIds) next.add(id);
      return next;
    });
  }, []);

  const resetBaseline = useCallback(() => {
    setSavedVersionIds(new Set());
  }, []);

  const fetchDocuments = useCallback(async (wsId: string) => {
    setLoadingDocuments(true);
    try {
      setDocuments(await api.listWorkspaceJsons(wsId));
    } finally {
      setLoadingDocuments(false);
    }
  }, []);

  // Bounded self-retry for rate-limited refreshes: a 429 on the boot fetch
  // must not strand the UI with an empty workspace list until a reload.
  const retryRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear any pending retry on unmount so it can't fire setState after teardown.
  useEffect(() => {
    return () => {
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
    };
  }, []);

  const refreshWorkspaces = useCallback(async () => {
    setLoadingWorkspaces(true);
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);
      retryRef.current = 0;
      // Restore selection from localStorage; fall back to the default ws.
      let saved: { workspaceId?: string | null; documentId?: string | null } = {};
      try {
        saved = JSON.parse(localStorage.getItem(WS_STORAGE_KEY) || '{}');
      } catch { /* ignore */ }
      const active =
        list.find((w) => w.id === saved.workspaceId) ??
        list.find((w) => w.is_default) ??
        list[0];
      if (active) {
        setActiveWorkspaceId(active.id);
        const docs = await api.listWorkspaceJsons(active.id);
        setDocuments(docs);
        const doc = docs.find((d) => d.id === saved.documentId);
        setActiveDocumentId(doc ? doc.id : null);
      }
    } catch (err: any) {
      // Loaded state stays as-is — never clear lists on a failed refresh.
      if (err?.status === 429 && retryRef.current < 3) {
        retryRef.current += 1;
        const wait = Number(err.retryAfter) || 30;
        toast.info(`Rate limited — retrying workspaces in ${wait}s`);
        retryTimeoutRef.current = setTimeout(() => { refreshWorkspaces(); }, wait * 1000);
        return;
      }
      if (!handleWorkspaceError(err)) toast.error(String(err?.message || err));
    } finally {
      setLoadingWorkspaces(false);
    }
  }, []);

  // Kick off once the session profile resolves to logged-in.
  const bootedRef = useRef(false);
  useEffect(() => {
    if (!loggedIn || bootedRef.current) return;
    bootedRef.current = true;
    refreshWorkspaces();
  }, [loggedIn, refreshWorkspaces]);

  // One-click save into the active document (Tier 1 auto-save). A first save
  // — no document yet — still needs a tag, so it opens the dialog.
  const saveActive = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    if (!activeWorkspaceId || !activeDocumentId) {
      return await showSaveDialog();
    }
    try {
      await saveWorkRef.current({
        workspaceId: activeWorkspaceId,
        documentId: activeDocumentId,
      });
      return true;
    } catch (err: any) {
      const detail = err?.detail;
      if (detail?.error === 'limit_exceeded') {
        toast.error('Version limit reached (5) — delete a version to save more.');
      } else if (!handleWorkspaceError(err)) {
        toast.error(String(err?.message || err));
      }
      return false;
    }
  }, [dirty, activeWorkspaceId, activeDocumentId]);

  // Switching context no longer interrupts with a modal: pending edits are
  // saved into the active document silently, then the switch proceeds. The
  // only stops are a first-ever save (needs a tag) or a hard save failure.
  const guardDirty = useCallback(async (): Promise<boolean> => {
    if (!dirty) return true;
    return await saveActive();
  }, [dirty, saveActive]);

  const selectWorkspace = useCallback(async (id: string) => {
    if (id === activeWorkspaceId) return;
    if (!(await guardDirty())) return;
    try {
      await fetchDocuments(id);
      setActiveWorkspaceId(id);
      setActiveDocumentId(null);
      persistSelection(id, null);
      // Fresh editor: the old workspace's content must not linger in the
      // session, or it shows up as "Current JSON (unsaved)" here and the
      // dirty guard would offer to save it INTO this workspace.
      await clearSession();
      resetBaseline();
    } catch (err: any) {
      if (!handleWorkspaceError(err)) toast.error(String(err?.message || err));
    }
  }, [activeWorkspaceId, guardDirty, fetchDocuments, clearSession, resetBaseline]);

  const createWorkspace = useCallback(async (name: string) => {
    const ws = await api.createWorkspace(name); // 409s rethrow for inline errors
    setWorkspaces((prev) => [...prev, ws]);
    return ws;
  }, []);

  const renameWorkspace = useCallback(async (id: string, name: string) => {
    const ws = await api.renameWorkspace(id, name);
    setWorkspaces((prev) => prev.map((w) => (w.id === id ? ws : w)));
  }, []);

  const deleteWorkspace = useCallback(async (id: string) => {
    try {
      await api.deleteWorkspace(id);
      const rest = workspaces.filter((w) => w.id !== id);
      setWorkspaces(rest);
      if (id === activeWorkspaceId) {
        const fallback = rest.find((w) => w.is_default) ?? rest[0] ?? null;
        setActiveWorkspaceId(fallback?.id ?? null);
        setActiveDocumentId(null);
        persistSelection(fallback?.id ?? null, null);
        if (fallback) await fetchDocuments(fallback.id);
        else setDocuments([]);
        // Same as selectWorkspace: deleted workspace's content must not
        // linger in the editor as "unsaved".
        await clearSession();
        resetBaseline();
      }
      toast.success('Workspace deleted');
    } catch (err: any) {
      if (!handleWorkspaceError(err)) toast.error(String(err?.message || err));
    }
  }, [workspaces, activeWorkspaceId, fetchDocuments, clearSession, resetBaseline]);

  // targetVersionId opens a specific version; defaults to the latest. It is
  // baked into the single restore call (working_json + active_version_id) so
  // there is NO follow-up selectVersion — that would hit a stale sessionId
  // closure (loadSnapshot just minted a new session) and 404.
  const loadDocument = useCallback(async (docId: string, targetVersionId?: string): Promise<boolean> => {
    if (!activeWorkspaceId) return false;
    if (docId === activeDocumentId && !targetVersionId) return true;
    if (!(await guardDirty())) return false;
    setLoadingDocuments(true);
    try {
      const doc = await api.getWorkspaceJson(activeWorkspaceId, docId);
      const target =
        (targetVersionId && doc.versions.find((v) => v.id === targetVersionId)) ||
        doc.versions[doc.versions.length - 1];
      // DB ids are reused as session version ids by the restore seam, so
      // savedVersionIds bookkeeping matches without an id map.
      await loadSnapshot({
        versions: doc.versions.map((v) => ({
          id: v.id,
          parent_id: null,
          json_data: v.content,
          label: v.label ?? `v${v.version_number}`,
          created_at: v.created_at,
        })),
        workingJson: target?.content ?? {},
        activeVersionId: target?.id ?? null,
      });
      setSavedVersionIds(new Set(doc.versions.map((v) => v.id)));
      setActiveDocumentId(docId);
      persistSelection(activeWorkspaceId, docId);
      toast.success(`Loaded "${doc.tag}" (v${target?.version_number ?? 1})`);
      return true;
    } catch (err: any) {
      if (!handleWorkspaceError(err)) toast.error(String(err?.message || err));
      return false;
    } finally {
      setLoadingDocuments(false);
    }
  }, [activeWorkspaceId, activeDocumentId, guardDirty, loadSnapshot]);

  const saveWork = useCallback(async (input: SaveInput) => {
    setSaving(true);
    try {
    // Build the payload: unsaved session versions first, dirty working copy on top.
    // Full payload, not pending-only: "save as new JSON" is a copy — with a
    // clean baseline pendingSave is empty and the save would no-op. The
    // append path dedupes by content below, so full input stays correct.
    const versions = [...fullSave.versions];
    if (fullSave.workingChanged) {
      versions.push({ label: 'Working copy', content: session.workingJson });
    }
    if (versions.length === 0) {
      toast.info('Nothing new to save.');
      return;
    }

    let wsId = input.workspaceId ?? activeWorkspaceId;
    if (input.newWorkspaceName) {
      const ws = await createWorkspace(input.newWorkspaceName); // 409 rethrows
      wsId = ws.id;
    }
    if (!wsId) throw new Error('No workspace selected');

    let docId = input.documentId ?? null;
    if (docId) {
      // Dedupe against what the document already holds: the dirty baseline
      // lives in React state and dies on reload, so without this a reload
      // followed by Save re-appends every session version as a duplicate
      // (and burns version slots). Content-level compare — session ids and
      // DB ids diverge for locally created versions, ids can't be trusted.
      const existing = await api.getWorkspaceJson(wsId, docId);
      const persisted = new Set(existing.versions.map((v) => canonicalJson(v.content)));
      const newOnly = versions.filter((v) => !persisted.has(canonicalJson(v.content)));
      if (newOnly.length === 0) {
        markClean(session.versions.map((v) => v.id));
        setActiveDocumentId(docId);
        persistSelection(wsId, docId);
        toast.info('Everything is already saved in this JSON.');
        return;
      }
      await api.appendJsonVersions(wsId, docId, { versions: newOnly });
    } else {
      if (!input.tag) throw new Error('Tag is required');
      const doc = await api.saveWorkspaceJson(wsId, { tag: input.tag, versions });
      docId = doc.id;
    }

    // Every session version is now represented in the target document.
    markClean(session.versions.map((v) => v.id));
    setActiveWorkspaceId(wsId);
    setActiveDocumentId(docId);
    persistSelection(wsId, docId);
    await Promise.all([
      fetchDocuments(wsId),
      api.listWorkspaces().then(setWorkspaces).catch(() => {}),
    ]);
    toast.success('Saved to workspace');
    } finally {
      setSaving(false);
    }
  }, [fullSave, session.workingJson, session.versions, activeWorkspaceId, createWorkspace, markClean, fetchDocuments]);

  // Keep the ref current so saveActive/guardDirty (declared earlier) call the
  // latest saveWork closure.
  saveWorkRef.current = saveWork;

  const deleteDocument = useCallback(async (docId: string) => {
    if (!activeWorkspaceId) return;
    try {
      await api.deleteWorkspaceJson(activeWorkspaceId, docId);
      if (docId === activeDocumentId) {
        setActiveDocumentId(null);
        persistSelection(activeWorkspaceId, null);
        resetBaseline();
      }
      await fetchDocuments(activeWorkspaceId);
      toast.success('JSON deleted');
    } catch (err: any) {
      if (!handleWorkspaceError(err)) toast.error(String(err?.message || err));
    }
  }, [activeWorkspaceId, activeDocumentId, fetchDocuments, resetBaseline]);

  const deleteVersion = useCallback(async (docId: string, versionId: string) => {
    if (!activeWorkspaceId) return;
    try {
      await api.deleteJsonVersion(activeWorkspaceId, docId, versionId);
      await fetchDocuments(activeWorkspaceId);
      toast.success('Version deleted');
    } catch (err: any) {
      if (handleWorkspaceError(err)) return;
      if (err?.status === 409) {
        toast.error('A JSON must keep at least one version — delete the JSON instead.');
        return;
      }
      toast.error(String(err?.message || err));
    }
  }, [activeWorkspaceId, fetchDocuments]);

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces,
        activeWorkspaceId,
        documents,
        activeDocumentId,
        limits: WORKSPACE_LIMITS,
        loadingWorkspaces,
        loadingDocuments,
        loggedIn,
        dirty,
        saving,
        status,
        saveActive,
        pendingSave,
        fullSave,
        refreshWorkspaces,
        createWorkspace,
        renameWorkspace,
        deleteWorkspace,
        selectWorkspace,
        loadDocument,
        saveWork,
        deleteDocument,
        deleteVersion,
        guardDirty,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
