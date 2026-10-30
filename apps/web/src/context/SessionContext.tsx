'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { toast } from 'sonner';
import * as api from '../lib/api';
import { saveWorkspace, loadWorkspace, clearWorkspace, MAX_CACHED_TURNS } from '../lib/versionCache';
import { pendingDiffs, syncStatuses, type UiChatTurn } from '../lib/chatHistory';
import { showRateLimitModal } from '../components/RateLimitModal';
import { showTooLargeModal } from '../components/TooLargeModal';
import { trackEvent } from '../lib/gtagConversion';

// A request is rate-limited when the backend answered HTTP 429 (status carried
// on the error) or the message otherwise mentions 429.
function isRateLimited(err: any): boolean {
  return err?.status === 429 || /\b429\b/.test(String(err?.message || ''));
}

// Monthly credits exhausted (HTTP 402). Anonymous callers can log in for
// their own free quota (err.loginAvailable, parsed from the response body).
function isCreditExhausted(err: any): boolean {
  return err?.status === 402;
}

// Deployment/provider failure (HTTP 503 with a structured detail). The
// backend hides raw provider errors and asks the user to retry shortly.
function isServiceBusy(err: any): boolean {
  return err?.status === 503 || err?.detail?.error === 'service_unavailable';
}

// Shared quota-error handling for catch blocks: shows the popup with the
// login CTA when applicable. Returns true when the error was a quota error.
function handleQuotaError(err: any): boolean {
  if (isServiceBusy(err)) {
    showRateLimitModal({
      scope: 'model',
      kind: 'busy',
      message: err.detail?.message,
      retryAfter: err.retryAfter,
    });
    return true;
  }
  if (isCreditExhausted(err)) {
    showRateLimitModal({
      scope: 'api',
      kind: 'credits',
      loginAvailable: err.loginAvailable === true,
    });
    return true;
  }
  if (isRateLimited(err)) {
    showRateLimitModal({
      scope: 'api',
      kind: 'rate',
      retryAfter: err.retryAfter,
      loginAvailable: err.loginAvailable === true,
    });
    return true;
  }
  return false;
}

// "search" / "read" tool calls → a short progress line for the chat bubble.
function describeToolCall(name: string, rawArgs?: string): string {
  let args: Record<string, any> = {};
  try { args = JSON.parse(rawArgs || '{}'); } catch { /* truncated args */ }
  if (name === 'search') return `Searching the document for “${args.query ?? '…'}”…`;
  if (name === 'read') return `Reading ${args.path || 'the document'}…`;
  return `Looking up ${name}…`;
}

type SessionVersion = {
  id: string;
  label: string;
  json_data: any;
  parent_id?: string | null;
  created_at?: string | null;
};

type SessionState = {
  sessionId: string | null;
  workingJson: Record<string, any>;
  baselineJson: Record<string, any>;
  versions: SessionVersion[];
  conversationHistory: UiChatTurn[]; // server-authoritative thread + diff statuses
  activeVersionId: string | null;
  loading: boolean;
  error: string | null;
  explainMarkdown: string | null;
  explaining: boolean;
  explainError: string | null;
  profile: Record<string, any> | null; // logged-in user profile + credits (GET /api/me)
};

type SessionContextValue = {
  state: SessionState;
  createSession: (name: string) => Promise<void>;
  uploadJson: (jsonData: Record<string, any>) => Promise<boolean>;
  sendMessage: (message: string, thinking?: boolean, focusPath?: string) => Promise<void>;
  acceptDiff: (diffId: string) => Promise<void>;
  createVersion: (label: string) => void;
  selectVersion: (versionId: string) => Promise<void>;
  exportJson: () => void;
  removeDiff: (diffId: string) => Promise<void>;
  acceptAllDiffs: () => Promise<void>;
  rejectAllDiffs: () => Promise<void>;
  refreshSession: () => Promise<void>;
  explainJson: () => Promise<void>;
  clearCache: () => Promise<void>;
  loadSnapshot: (payload: {
    versions: Array<{ id: string; parent_id: string | null; json_data: Record<string, any>; label: string; created_at: string }>;
    workingJson: Record<string, any>;
    activeVersionId: string | null;
  }) => Promise<void>;
  clearSession: () => Promise<void>;
  clearChat: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

// Keep parent_id/created_at so IndexedDB snapshots restore with full fidelity
const mapVersions = (versions: any[] | undefined): SessionVersion[] =>
  (versions || []).map((v: any) => ({
    id: v.id, label: v.label, json_data: v.json_data,
    parent_id: v.parent_id ?? null, created_at: v.created_at ?? null,
  }));

export function SessionProvider({ children }: { children: React.ReactNode }) {
    // API key read via useEffect -- never during SSR render
  const [apiKey, setApiKey] = useState<string>('');

  useEffect(() => {
    let key = localStorage.getItem('json-ai-studio-api-key');
    if (!key) {
      key = crypto.randomUUID();
      localStorage.setItem('json-ai-studio-api-key', key);
      }
    setApiKey(key);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

  const [state, setState] = useState<SessionState>({
    sessionId: null, workingJson: {}, baselineJson: {}, versions: [],
    conversationHistory: [], activeVersionId: null,
    loading: true, error: null, explainMarkdown: null,
    explaining: false, explainError: null, profile: null,
    });

    // Fetch the logged-in user's profile + quota (null when anonymous).
  useEffect(() => {
    api.getMe()
      .then((profile) => {
        if (profile) setState((prev) => ({ ...prev, profile }));
        })
      .catch(() => {});
    }, []);

    // Hydrate: backend session if alive, else restore from IndexedDB cache.
    // Ref guard: StrictMode double-mount must not create two backend sessions.
  const restoreStartedRef = useRef(false);

  useEffect(() => {
    if (!apiKey) return;
    if (restoreStartedRef.current) return;
    restoreStartedRef.current = true;

    const hydrated = (sessionId: string, data: any) => setState((prev) => ({
      ...prev,
      sessionId,
      workingJson: (data.working_json as Record<string, any>) || {},
      baselineJson: (data.baseline_json as Record<string, any>) || {},
      versions: mapVersions(data.versions),
      conversationHistory: (data.conversation_history as UiChatTurn[]) || [],
      activeVersionId: (data.active_version_id as string) || null,
      loading: false,
      error: null,
      explainMarkdown: null,
      explaining: false,
      explainError: null,
      }));

    const hydrate = async () => {
      let savedSessionId: string | null = null;
      const saved = localStorage.getItem('json-ai-studio-session');
      if (saved) {
        try {
          savedSessionId = JSON.parse(saved).sessionId ?? null;
          } catch {
          localStorage.removeItem('json-ai-studio-session');
          }
        }

      const cached = await loadWorkspace();

      if (savedSessionId) {
        try {
          const data = await api.getSession(savedSessionId, apiKey);
          hydrated(savedSessionId, data);
          return;
          } catch (err: any) {
          if (err?.status !== 404) {
              // Backend down/unreachable -- keep localStorage + cache so the
              // next reload can retry; do NOT create a new session.
            toast.error('Backend unreachable. Your cached data is kept for the next reload.');
            setState((prev) => ({ ...prev, loading: false }));
            return;
            }
            // 404: backend lost the session (restart) -- fall through to restore
          }
        }

      const hasCache = !!cached && (
        (cached.versions?.length ?? 0) > 0 ||
        Object.keys(cached.workingJson || {}).length > 0
        );
      if (hasCache) {
        try {
          const sess = await api.createSession('Restored', apiKey);
          const data = await api.restoreVersions(sess.id, {
            versions: cached!.versions,
            working_json: cached!.workingJson,
            baseline_json: cached!.baselineJson,
            active_version_id: cached!.activeVersionId,
            conversation_history: cached!.conversationHistory || [],
            }, apiKey);
          localStorage.setItem('json-ai-studio-session', JSON.stringify({ sessionId: sess.id }));
          hydrated(sess.id, data);
          toast.success(`Restored ${cached!.versions.length} version(s) from browser cache.`);
          return;
          } catch {
            // Keep IndexedDB intact so the next reload can retry the restore
          localStorage.removeItem('json-ai-studio-session');
          toast.warning('Session expired. Cached versions could not be restored — will retry on next reload.');
          setState((prev) => ({ ...prev, loading: false }));
          return;
          }
        }

      if (savedSessionId) {
        localStorage.removeItem('json-ai-studio-session');
        toast.warning('Session expired. Starting fresh.');
        }
      setState((prev) => ({ ...prev, loading: false }));
      };

    hydrate();
    }, [apiKey]);

    // Mirror workspace to IndexedDB (debounced) so versions + unsaved work
    // survive backend restarts. One effect covers every state mutation path.
  useEffect(() => {
    if (state.loading || !state.sessionId) return;
    const t = setTimeout(() => {
      saveWorkspace({
        sessionId: state.sessionId,
        versions: state.versions.map((v) => ({
          id: v.id,
          parent_id: v.parent_id ?? null,
          json_data: v.json_data,
          label: v.label,
          created_at: v.created_at ?? new Date().toISOString(),
          })),
        workingJson: state.workingJson,
        baselineJson: state.baselineJson,
        activeVersionId: state.activeVersionId,
        conversationHistory: state.conversationHistory
          .filter((t) => !t.ephemeral)
          .slice(-MAX_CACHED_TURNS)
          .map(({ ephemeral: _e, ...t }) => t),
        updatedAt: new Date().toISOString(),
        });
      }, 500);
    return () => clearTimeout(t);
    }, [state.sessionId, state.versions, state.workingJson, state.baselineJson, state.activeVersionId, state.conversationHistory, state.loading]);

  const updateSessionStorage = (sessionId: string) => {
    localStorage.setItem('json-ai-studio-session', JSON.stringify({ sessionId }));
    };

  const createSession = useCallback(async (name: string) => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const data = await api.createSession(name, apiKey);
      updateSessionStorage(data.id);
      setState({
          ...state,
        sessionId: data.id,
        workingJson: (data.working_json as Record<string, any>) || {},
        versions: mapVersions(data.versions),
        conversationHistory: [],
        loading: false,
        error: null,
        explainMarkdown: null,
        explaining: false,
        explainError: null,
        });
      } catch (err: any) {
      if (handleQuotaError(err)) {
        // popup shown
        } else if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('Auth required. Refresh the page to get a new key.');
        } else {
        toast.error(String(err));
        }
      setState({ ...state, error: String(err), loading: false });
      }
    }, [apiKey, state]);

  const uploadJson = useCallback(async (jsonData: Record<string, any>) => {
      // No createSession pre-call: the upload endpoint creates/reuses a session,
      // and createSession flips `loading` which unmounts the whole app tree
      // (provider renders null), losing page-local UI state mid-upload.
    try {
      const data = await api.uploadJson(
        JSON.stringify(jsonData), undefined, apiKey, state.sessionId || undefined,
        );
      if (data?.session_id) updateSessionStorage(data.session_id);
        // Store parsed_json as workingJson so the UI can render it immediately
      setState((prev) => ({...prev,
        sessionId: data.session_id || prev.sessionId,
        workingJson: data.after || data.parsed_json || prev.workingJson,
        baselineJson: data.before || data.parsed_json || {},
        conversationHistory: [], // new document → backend dropped the thread
        error: null,
        loading: false,
        explainMarkdown: null,
        explainError: null,
        }));
      toast.success('JSON loaded');
      trackEvent('json_upload');
      return true;
      } catch (err: any) {
      if (handleQuotaError(err)) {
        // popup shown
        } else if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('Auth required. Refresh page to get a new key.');
        } else {
        toast.error(String(err));
        }
      setState((prev) => ({ ...prev, error: String(err) }));
      return false;
      }
    }, [state.sessionId, apiKey]);

  const sendMessage = useCallback(async (message: string, thinking: boolean = false, focusPath?: string) => {
    if (!state.sessionId) return;

         // 1. Snapshot the initial payload variables
    const currentWorkingJson = JSON.parse(JSON.stringify(state.workingJson));
    // Optimistic turns get temp ids; the `complete` event swaps in the
    // server ids. Stays ephemeral (never mirrored) if the server didn't
    // store the turn (quota stop / error).
    const tempUserId = `local-u-${Date.now()}`;
    const tempAssistantId = `local-a-${Date.now()}`;

    setState((prev) => ({
        ...prev,
      loading: false,
      conversationHistory: [
        ...prev.conversationHistory,
        {
          id: tempUserId,
          role: 'user',
          content: focusPath ? `${message}\n\n(Section: ${focusPath})` : message,
          ephemeral: true,
        },
      ]
      }));

    try {
        // Track streaming variables locally
      let activeJson = currentWorkingJson;
      let baselineJson = state.baselineJson || {};
      const diffs: any[] = [];
      let textAccumulator = '';
      let stored: { userId: string; assistantId: string } | null = null;
      let quotaStopped = false;
      let question: { text: string; options: string[] } | null = null;
      // Progress line while the backend runs lookup tools on a large doc
      // (ADR-0024); replaced by the explanation on `complete`.
      let toolStatus = '';

        // Initialize the assistant message container in UI history
      setState((prev) => ({
          ...prev,
        conversationHistory: [
            ...prev.conversationHistory,
            { id: tempAssistantId, role: 'assistant', content: '', diffs: [], ephemeral: true }
          ]
        }));

        // 2. Stream loop
      for await (const chunk of api.streamChat(state.sessionId, message, currentWorkingJson, apiKey, thinking, focusPath)) {

        // Model-level quota/availability events: backend streams a
        // `rate_limit`, `credit_limit` or `service_unavailable` event
        // instead of a diff/complete. Show the popup (with a login CTA for
        // anonymous users on quota errors) and stop consuming.
        if (
          chunk.type === 'rate_limit' ||
          chunk.type === 'credit_limit' ||
          chunk.type === 'service_unavailable'
        ) {
          showRateLimitModal({
            scope: chunk.data?.scope || 'model',
            kind:
              chunk.type === 'credit_limit'
                ? 'credits'
                : chunk.type === 'service_unavailable'
                  ? 'busy'
                  : chunk.data?.scope === 'model'
                    ? 'capacity' // AI model per-minute limit, not the user's (ADR-0025)
                    : 'rate',
            message: chunk.data?.message,
            retryAfter: chunk.data?.retry_after,
            loginAvailable: chunk.data?.login_available === true,
          });
          quotaStopped = true;
          break;
          }

        // Document cannot fit the model even trimmed (ADR-0025): nothing was
        // sent and no credits used. Offer sections / a trimmed copy.
        if (chunk.type === 'input_too_large') {
          showTooLargeModal({ ...chunk.data, userMessage: message, thinking });
          quotaStopped = true;
          break;
          }

        let structureChanged = false;

        if (chunk.type === 'diff' && chunk.data.entry) {
          diffs.push(chunk.data.entry);
          structureChanged = true;
          } else if (chunk.type === 'complete' && chunk.data.working_json) {
            // Capture the brand new JSON emitted from your API response
          activeJson = chunk.data.working_json;
          if (chunk.data.baseline_json !== undefined) {
            baselineJson = chunk.data.baseline_json;
            }
            // Also extract explanation text from the complete event payload
          if (chunk.data.explanation) {
            textAccumulator += String(chunk.data.explanation);
            }
          if (chunk.data.user_turn_id && chunk.data.assistant_turn_id) {
            stored = { userId: chunk.data.user_turn_id, assistantId: chunk.data.assistant_turn_id };
            }
          if (chunk.data.question?.text) {
            question = chunk.data.question;
            }
          structureChanged = true;
          } else if (chunk.type === 'tool' && chunk.data?.name) {
          toolStatus = describeToolCall(chunk.data.name, chunk.data.args);
          structureChanged = true;
          } else if (chunk.type === 'waiting') {
          // Deployment budget wait (ADR-0025); the turn continues after it.
          toolStatus = `Waiting for AI model capacity… ~${chunk.data?.retry_after ?? ''}s`;
          structureChanged = true;
          } else if (chunk.type === 'content' || chunk.type === 'text') {
          textAccumulator += chunk.data.text || '';
            // Backend may embed explanation alongside working_json in content/text chunks
          if (chunk.data.explanation) {
            textAccumulator += String(chunk.data.explanation);
            }
          structureChanged = true;
          }

            // 3. CRITICAL: Update both History AND Working JSON simultaneously
        if (structureChanged) {
          ReactDOM.flushSync(() => {
            setState((prev) => {
              const historyCopy = [...prev.conversationHistory];
              if (historyCopy.length > 0) {
                const lastIndex = historyCopy.length - 1;
                historyCopy[lastIndex] = {
                    ...historyCopy[lastIndex],
                  content: textAccumulator || toolStatus,
                  diffs: [...diffs],
                  question,
                  };
                }

                    return {
                         ...prev,
                        conversationHistory: historyCopy,
                          // Use activeJson if updated, otherwise fallback to the absolutely latest prev state
                        workingJson: activeJson || currentWorkingJson,
                        baselineJson: baselineJson || prev.baselineJson
                     };
                 });
             });
         }
         }

        // 4. Stream finalized: adopt server ids, or drop/keep-local the
        // optimistic pair when the backend did not store the turn.
      const storedIds = stored as { userId: string; assistantId: string } | null;
      ReactDOM.flushSync(() => {
        setState((prev) => {
          let history = prev.conversationHistory;
          if (quotaStopped) {
            history = history.filter((t) => t.id !== tempUserId && t.id !== tempAssistantId);
            } else if (storedIds) {
            history = history.map((t) =>
              t.id === tempUserId ? { ...t, id: storedIds.userId, ephemeral: false }
                : t.id === tempAssistantId ? { ...t, id: storedIds.assistantId, ephemeral: false }
                : t);
            }
          return { ...prev, conversationHistory: history, loading: false, error: null };
          });
        });

      } catch (err: any) {
      if (handleQuotaError(err)) {
        // popup shown
        } else if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('API key rejected. Refresh page.');
        } else {
        toast.error(String(err));
        }
      setState((prev) => ({ ...prev, error: String(err), loading: false }));
      }
    }, [ state.workingJson, apiKey]);


  const acceptDiff = useCallback(async (diffId: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.acceptDiff(state.sessionId, diffId, apiKey);
      setState(prev => ({
        ...prev,
        workingJson: data.working_json,
        baselineJson: data.baseline_json || prev.baselineJson,
        conversationHistory: syncStatuses(prev.conversationHistory, data.conversation_history),
        }));
      } catch (err: any) {
      toast.error(err?.status === 409 ? 'That change was already resolved.' : String(err));
      }
    }, [state.sessionId, apiKey]);

  const createVersion = useCallback(async ( label: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.createVersion(state.sessionId, label, state.workingJson, apiKey);
      setState(prev => ({
          ...prev,
        workingJson: data.json_data || data.working_json || prev.workingJson,
        activeVersionId: data.id || prev.activeVersionId,
        versions: [...prev.versions, {
          id: data.id, label: data.label, json_data: data.json_data,
          parent_id: data.parent_id ?? null, created_at: data.created_at ?? null,
          }],
        }));
      } catch (err: any) { toast.error(String(err)); }
    }, [state.sessionId, state.workingJson, apiKey]);
  const removeDiff = useCallback(async (diffId: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.rejectDiff(state.sessionId, diffId, apiKey);
      setState(prev => ({
        ...prev,
        workingJson: data.working_json,
        baselineJson: data.baseline_json || prev.baselineJson,
        conversationHistory: syncStatuses(prev.conversationHistory, data.conversation_history),
        }));
      } catch (err: any) {
      toast.error(err?.status === 409 ? 'That change was already resolved.' : String(err));
      }
    }, [state.sessionId, apiKey]);

  const acceptAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.acceptDiffBatch(state.sessionId, apiKey);
      setState(prev => ({
        ...prev,
        workingJson: data.working_json,
        baselineJson: data.baseline_json || prev.baselineJson,
        conversationHistory: syncStatuses(prev.conversationHistory, data.conversation_history),
        }));
      } catch (err: any) {
      toast.error(err?.status === 409 ? 'That change was already resolved.' : String(err));
      }
    }, [state.sessionId, apiKey]);

  const rejectAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.rejectDiffBatch(state.sessionId, apiKey);
      setState(prev => ({
        ...prev,
        workingJson: data.working_json,
        baselineJson: data.baseline_json || prev.baselineJson,
        conversationHistory: syncStatuses(prev.conversationHistory, data.conversation_history),
        }));
      } catch (err: any) {
      toast.error(err?.status === 409 ? 'That change was already resolved.' : String(err));
      }
    }, [state.sessionId, apiKey]);


  const refreshSession = useCallback(async () => {
    if (!state.sessionId || !apiKey) return;
    try {
      const data = await api.getSession(state.sessionId, apiKey);
      setState(prev => ({
          ...prev,
        workingJson: (data.working_json as Record<string, any>) || {},
        baselineJson: (data.baseline_json as Record<string, any>) || {},
        activeVersionId: (data.active_version_id as string) || null,
        versions: mapVersions(data.versions),
        }));
      } catch (err: any) { toast.error(String(err)); }
    }, [state.sessionId, apiKey]);

  // Load an external snapshot set (a workspace document, ADR-0018) into a
  // FRESH session: the restore endpoint only accepts sessions with no
  // versions, so we mint one — same flow the IndexedDB boot restore uses.
  // Does not touch the global `loading` flag (tree would unmount).
  const loadSnapshot = useCallback(async (payload: {
    versions: Array<{ id: string; parent_id: string | null; json_data: Record<string, any>; label: string; created_at: string }>;
    workingJson: Record<string, any>;
    activeVersionId: string | null;
  }) => {
    const sess = await api.createSession('Workspace JSON', apiKey);
    const data = await api.restoreVersions(sess.id, {
      versions: payload.versions,
      working_json: payload.workingJson,
      baseline_json: payload.workingJson,
      active_version_id: payload.activeVersionId,
      }, apiKey);
    updateSessionStorage(sess.id);
    setState((prev) => ({
      ...prev,
      sessionId: sess.id,
      workingJson: (data.working_json as Record<string, any>) || payload.workingJson,
      baselineJson: (data.baseline_json as Record<string, any>) || payload.workingJson,
      versions: mapVersions(data.versions),
      conversationHistory: [],
      activeVersionId: (data.active_version_id as string) ?? payload.activeVersionId,
      error: null,
      explainMarkdown: null,
      explaining: false,
      explainError: null,
      }));
    }, [apiKey]);

  // Fresh empty session — used when switching workspaces so content from the
  // previous workspace never lingers as "unsaved" in the new one. Never
  // touches the global `loading` flag (the provider unmounts on it).
  const clearSession = useCallback(async () => {
    const sess = await api.createSession('My Config', apiKey);
    updateSessionStorage(sess.id);
    setState((prev) => ({
      ...prev,
      sessionId: sess.id,
      workingJson: {},
      baselineJson: {},
      versions: [],
      conversationHistory: [],
      activeVersionId: null,
      error: null,
      explainMarkdown: null,
      explaining: false,
      explainError: null,
    }));
  }, [apiKey]);

  // Clear the chat thread (model context). Backend refuses (409) while
  // diffs are pending — offer to resolve them first, then retry.
  const clearChat = useCallback(async () => {
    if (!state.sessionId) return;
    const sessionId = state.sessionId;
    const doClear = async () => {
      await api.clearChat(sessionId, apiKey);
      setState((prev) => ({ ...prev, conversationHistory: [] }));
      toast.success('Chat cleared');
      };
    try {
      await doClear();
      } catch (err: any) {
      if (err?.status !== 409) { toast.error(String(err)); return; }
      const n = pendingDiffs(state.conversationHistory).length;
      const resolveThen = (fn: typeof api.acceptDiffBatch) => async () => {
        try {
          const data = await fn(sessionId, apiKey);
          setState((prev) => ({ ...prev, workingJson: data.working_json, baselineJson: data.baseline_json || prev.baselineJson }));
          await doClear();
          } catch (e: any) { toast.error(String(e)); }
        };
      toast.warning(`${n || 'Some'} change(s) still pending. Resolve them before clearing.`, {
        action: { label: 'Accept all', onClick: resolveThen(api.acceptDiffBatch) },
        cancel: { label: 'Reject all', onClick: resolveThen(api.rejectDiffBatch) },
        duration: 10000,
        });
      }
    }, [state.sessionId, state.conversationHistory, apiKey]);

  const [unsavedChangesModalOpen, setUnsavedChangesModalOpen] = useState(false);
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);

  function deepEqual(a: any, b: any): boolean {
    return JSON.stringify(a) === JSON.stringify(b);
   }

  const callSelectVersion = async (versionId: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.selectVersion(state.sessionId, versionId, apiKey);
      setState({
          ...state,
        workingJson: data.working_json || {},
        baselineJson: data.baseline_json || {},
        conversationHistory: (data.conversation_history as UiChatTurn[]) || [],
        activeVersionId: data.active_version_id,
        loading: false,
        error: null,
        explainMarkdown: null,
        explainError: null,
        });
      } catch (err: any) {
      toast.error(String(err));
      setState(prev => ({ ...prev, error: String(err), loading: false }));
      }
     };

  const handleSaveAndContinue = async () => {
    if (!state.sessionId) return;
    try {
      await api.createVersion(state.sessionId, 'Auto-save before switch', state.workingJson, apiKey);
      if (pendingVersionId) {
        await callSelectVersion(pendingVersionId);
        }
      } catch (err: any) {
      toast.error('Failed to save. Please try again.');
      } finally {
      setUnsavedChangesModalOpen(false);
      setPendingVersionId(null);
      }
     };

  const handleDiscardAndContinue = () => {
    if (pendingVersionId) {
      callSelectVersion(pendingVersionId).finally(() => {
        setUnsavedChangesModalOpen(false);
        setPendingVersionId(null);
        });
      }
     };

  const selectVersion = useCallback(async (versionId: string) => {
    if (!deepEqual(state.workingJson, state.baselineJson || {})) {
      setPendingVersionId(versionId);
      setUnsavedChangesModalOpen(true);
      return;
       }
    await callSelectVersion(versionId);
     }, [state.sessionId, state.workingJson, state.baselineJson, apiKey]);


  const explainJson = useCallback(async () => {
    if (!state.sessionId || !Object.keys(state.workingJson).length) return;
      // Dedicated explain flags -- never touch the global `loading` flag here,
      // the provider unmounts the whole app while `loading` is true.
    setState((prev) => ({ ...prev, explaining: true, explainError: null }));
    try {
      const markdown = await api.explain(state.sessionId, state.workingJson, apiKey);
      setState((prev) => ({
         ...prev,
        explainMarkdown: markdown,
        explaining: false,
        explainError: null,
         }));
       } catch (err: any) {
      const popupShown = handleQuotaError(err);
      if (!popupShown) {
        toast.error(String(err));
        }
      setState((prev) => ({
        ...prev,
        // Popup already explains quota/busy errors; keep the panel text
        // short instead of dumping the raw response body.
        explainError: popupShown
          ? 'Service temporarily unavailable. Please try again shortly.'
          : String(err),
        explaining: false,
      }));
       }
     }, [state.sessionId, state.workingJson, apiKey]);

  const exportJson = useCallback(() => {
    if (!state.sessionId) return;
    const jsonStr = JSON.stringify(state.workingJson, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'config.json';
    a.click();
    URL.revokeObjectURL(url);
    }, [state]);

  const clearCache = useCallback(async () => {
    await clearWorkspace();
    toast.success('Cached versions cleared from this browser.');
    }, []);

    // Block UI until initial session data loaded from backend
  if (state.loading) return null;

  return (
      <SessionContext.Provider value={{ state, createSession, uploadJson, sendMessage, acceptDiff, createVersion, selectVersion, exportJson, removeDiff, acceptAllDiffs, rejectAllDiffs, refreshSession, explainJson, clearCache, loadSnapshot, clearSession, clearChat }}>
        {children}
      </SessionContext.Provider>
    );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
