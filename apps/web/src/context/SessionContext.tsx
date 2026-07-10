'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { toast } from 'sonner';
import * as api from '../lib/api';
import { saveWorkspace, loadWorkspace, clearWorkspace } from '../lib/versionCache';
import { showRateLimitModal } from '../components/RateLimitModal';

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
  conversationHistory: Array<{ role: string; content: string; diffs?: any[]; explanation?: string }>;
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
  uploadJson: (jsonData: Record<string, any>) => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
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
      conversationHistory: [],
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
        updatedAt: new Date().toISOString(),
        });
      }, 500);
    return () => clearTimeout(t);
    }, [state.sessionId, state.versions, state.workingJson, state.baselineJson, state.activeVersionId, state.loading]);

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
    if (!state.sessionId) {
      await createSession('Uploaded');
      }
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
        error: null,
        loading: false,
        explainMarkdown: null,
        explainError: null,
        }));
      } catch (err: any) {
      if (handleQuotaError(err)) {
        // popup shown
        } else if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('Auth required. Refresh page to get a new key.');
        } else {
        toast.error(String(err));
        }
      setState((prev) => ({ ...prev, error: String(err) }));
      }
    }, [state.sessionId, createSession, apiKey]);

  const sendMessage = useCallback(async (message: string) => {
    console.log('[SessionContext] sendMessage ENTRY called, messageLen:', message.length, 'sessionId:', state.sessionId, 'workingJsonKeys:', Object.keys(state.workingJson).length);
    if (!state.sessionId) {
      console.warn('[SessionContext] sendMessage early-return: no sessionId');
      return;
      }

         // 1. Snapshot the initial payload variables
    const currentWorkingJson = JSON.parse(JSON.stringify(state.workingJson));
    console.log('[SessionContext] Snapshot workingJson, keys:', Object.keys(currentWorkingJson));

    setState((prev) => ({
        ...prev,
      loading: false,
      conversationHistory: [...prev.conversationHistory, { role: 'user', content: message }]
      }));
    console.log('[SessionContext] SET_STATE: loading=true, added user message to history');

    try {
        // Track streaming variables locally
      let activeJson = currentWorkingJson;
      let baselineJson = state.baselineJson || {};
      const diffs: any[] = [];
      let textAccumulator = '';

        // Initialize the assistant message container in UI history
      setState((prev) => ({
          ...prev,
        conversationHistory: [
            ...prev.conversationHistory,
            { role: 'assistant', content: '', diffs: [] }
          ]
        }));
      console.log('[SessionContext] Initialized assistant message container in history');

        // 2. Stream loop
      console.log('[SessionContext] Starting stream loop over api.streamChat...');
      let chunkCount = 0;
      for await (const chunk of api.streamChat(state.sessionId, message, currentWorkingJson, apiKey)) {
        chunkCount++;
        console.log('[SessionContext] Chunk #' + chunkCount + ':', JSON.stringify(chunk).slice(0, 200));

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
                  : 'rate',
            message: chunk.data?.message,
            retryAfter: chunk.data?.retry_after,
            loginAvailable: chunk.data?.login_available === true,
          });
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
          structureChanged = true;
          console.log('[SessionContext] Received COMPLETE event, working_json keys:', Object.keys(activeJson));
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
          console.log('[SessionContext] structureChanged=true, diffCount=', diffs.length, 'textLen=', textAccumulator.length);
          ReactDOM.flushSync(() => {
            setState((prev) => {
              const historyCopy = [...prev.conversationHistory];
              if (historyCopy.length > 0) {
                const lastIndex = historyCopy.length - 1;
                historyCopy[lastIndex] = {
                    ...historyCopy[lastIndex],
                  content: textAccumulator,
                  diffs: [...diffs]
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
            console.log('[SessionContext] SET_STATE after chunk #' + chunkCount + ' flushed');
         }
         }

        // 4. Stream finalized successfully
      console.log('[SessionContext] Stream loop finished, totalChunks=', chunkCount);
      ReactDOM.flushSync(() => {
        setState((prev) => ({
            ...prev,
          loading: false,
          error: null
          }));
        });
      console.log('[SessionContext] SET_STATE: loading=false, error=null');

      } catch (err: any) {
      console.error('[SessionContext] sendMessage caught exception:', err?.message || String(err));
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
      setState(prev => {
        const history = [...prev.conversationHistory];
        if (history.length > 0) {
          const last = { ...history[history.length - 1] };
          last.diffs = (last.diffs || []).filter((d: any) => d.id !== diffId);
          history[history.length - 1] = last;
          }
        return { ...prev, workingJson: data.working_json, baselineJson: data.baseline_json || prev.baselineJson, conversationHistory: [...history] };
        });
      } catch (err: any) { toast.error(String(err)); }
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
      setState(prev => {
        const history = [...prev.conversationHistory];
        if (history.length > 0) {
          const last = { ...history[history.length - 1] };
          last.diffs = (last.diffs || []).filter((d: any) => d.id !== diffId);
          history[history.length - 1] = last;
          }
        return { ...prev, workingJson: data.working_json, baselineJson: data.baseline_json || prev.baselineJson, conversationHistory: [...history] };
        });
      } catch (err: any) { toast.error(String(err)); }
    }, [state.sessionId, apiKey]);

  const acceptAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.acceptDiffBatch(state.sessionId, apiKey);
      setState(prev => {
        const history = [...prev.conversationHistory];
        if (history.length > 0) {
          const last = { ...history[history.length - 1] };
          last.diffs = [];
          history[history.length - 1] = last;
          }
        return { ...prev, workingJson: data.working_json, baselineJson: data.baseline_json || prev.baselineJson, conversationHistory: [...history] };
        });
      } catch (err: any) { toast.error(String(err)); }
    }, [state.sessionId, apiKey]);

  const rejectAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.rejectDiffBatch(state.sessionId, apiKey);
      setState(prev => {
        const history = [...prev.conversationHistory];
        if (history.length > 0) {
          const last = { ...history[history.length - 1] };
          last.diffs = [];
          history[history.length - 1] = last;
          }
        return { ...prev, workingJson: data.working_json, baselineJson: data.baseline_json || prev.baselineJson, conversationHistory: [...history] };
        });
      } catch (err: any) { toast.error(String(err)); }
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
        conversationHistory: [],
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
      // build a data-URI blob for download
    const jsonStr = JSON.stringify(state.workingJson, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
    }, [state]);

  const clearCache = useCallback(async () => {
    await clearWorkspace();
    toast.success('Cached versions cleared from this browser.');
    }, []);

    // Block UI until initial session data loaded from backend
  if (state.loading) return null;

  return (
      <SessionContext.Provider value={{ state, createSession, uploadJson, sendMessage, acceptDiff, createVersion, selectVersion, exportJson, removeDiff, acceptAllDiffs, rejectAllDiffs, refreshSession, explainJson, clearCache }}>
        {children}
      </SessionContext.Provider>
    );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
