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
import { applyProgressEvent, legacyProgressText, newProgress, type TurnProgress } from '../lib/progress';
import { newJobUi, phaseOf, type JobPhase, type JobUi } from '../lib/reviewJob';

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
  conversationHistory: UiChatTurn[]; // server-authoritative thread + diff statuses
  activeVersionId: string | null;
  loading: boolean;
  error: string | null;
  explainMarkdown: string | null;
  explaining: boolean;
  explainError: string | null;
  profile: Record<string, any> | null; // logged-in user profile + credits (GET /api/me)
  job: JobUi | null; // whole-document review job of this session (ADR-0026)
};

type SessionContextValue = {
  state: SessionState;
  createSession: (name: string) => Promise<void>;
  uploadJson: (jsonData: Record<string, any>) => Promise<boolean>;
  /** false when the message was not sent (e.g. refused while a review batch runs). */
  sendMessage: (message: string, thinking?: boolean, focusPath?: string) => Promise<boolean>;
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
  // Whole-document review job (ADR-0026): the client asks for one batch at
  // a time; pausing stops asking, closing the tab pauses too.
  startJob: (proposal: api.JobProposal, sourceTurnId?: string) => Promise<void>;
  pauseJob: () => void;
  resumeJob: () => void;
  cancelJob: () => Promise<void>;
  dismissJob: () => void;
  acceptJobBatch: (jobId: string, batchNo: number) => Promise<void>;
  rejectJobBatch: (jobId: string, batchNo: number) => Promise<void>;
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
    explaining: false, explainError: null, profile: null, job: null,
    });

    // Review-job loop control (ADR-0026). A ref, not state: the loop reads it
    // between batches without re-rendering.
  const jobLoopRef = useRef<{ active: boolean; pause: boolean; cancel: boolean; abort: (() => void) | null }>(
    { active: false, pause: false, cancel: false, abort: null });
  // Chat turns streaming in this tab: the job loop waits for them before
  // asking for the next batch, so a question is not queued behind a batch
  // that fills the model's per-minute budget.
  const chatInFlightRef = useRef(0);
  // Unmount (or a dev Fast Refresh remount) must not leave a loop asking
  // for batches that nothing shows.
  useEffect(() => () => {
    jobLoopRef.current.pause = true;
    jobLoopRef.current.abort?.();
    }, []);
  const stopJobLoop = () => { jobLoopRef.current.pause = true; };

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
      job: null,
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
          // An unfinished review comes back PAUSED — never auto-run (WC-06).
          if (data.active_job_id) {
            try {
              const job = await api.getJob(savedSessionId, data.active_job_id, apiKey);
              setState((prev) => ({ ...prev, job: newJobUi(job) }));
              } catch { /* job gone with a backend restart */ }
            }
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
        job: null,
        });
      stopJobLoop();
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
        job: null, // …and cancelled its review job
        error: null,
        loading: false,
        explainMarkdown: null,
        explainError: null,
        }));
      stopJobLoop();
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

  const sendMessage = useCallback(async (message: string, thinking: boolean = false, focusPath?: string): Promise<boolean> => {
    if (!state.sessionId) return false;
    chatInFlightRef.current += 1;
    try {
      return await sendMessageInner(message, thinking, focusPath);
      } finally {
      chatInFlightRef.current -= 1;
      }
    }, [state.workingJson, state.sessionId, apiKey]);

  const sendMessageInner = async (message: string, thinking: boolean, focusPath?: string): Promise<boolean> => {
    if (!state.sessionId) return false;

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
      let activeJson: Record<string, any> | null = null; // set by `complete`
      let baselineJson: Record<string, any> | null = null;
      const diffs: any[] = [];
      let textAccumulator = '';
      let stored: { userId: string; assistantId: string } | null = null;
      let quotaStopped = false;
      let question: { text: string; options: string[] } | null = null;
      // Whole-document review too large for one turn (ADR-0026): the server
      // proposes a batch job instead of calling the model.
      let jobProposal: api.JobProposal | null = null;
      // Turn progress (PRD B §8): plan, step X/N, finished lookups, waits
      // and retries, folded from plan/progress/tool/waiting/retrying events
      // and rendered by ChatPanel's progress panel. Older backends send only
      // tool/waiting → legacyProgressText() as the bubble text.
      let progress = newProgress();

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
        const progressNext: TurnProgress | null = applyProgressEvent(progress, chunk.type, chunk.data);

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
          if (chunk.data.job_proposal) {
            jobProposal = chunk.data.job_proposal;
            }
          structureChanged = true;
          } else if (progressNext) {
          progress = progressNext;
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
              // By id, not "the last turn": a review batch may append its own
              // turn while this one streams (ADR-0026).
              const lastIndex = historyCopy.findIndex((t) => t.id === tempAssistantId);
              if (lastIndex >= 0) {
                historyCopy[lastIndex] = {
                    ...historyCopy[lastIndex],
                  content: textAccumulator || (progress.structured ? '' : legacyProgressText(progress)),
                  progress: textAccumulator ? { ...progress, finishedAt: progress.finishedAt ?? Date.now() } : progress,
                  diffs: [...diffs],
                  question,
                  ...(jobProposal ? { kind: 'job_proposal' as const, job_proposal: jobProposal } : {}),
                  };
                }

                    return {
                         ...prev,
                        conversationHistory: historyCopy,
                          // Only `complete` carries a new document; until then keep
                          // the latest state (a review batch may have changed it).
                        workingJson: activeJson || prev.workingJson,
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
      if (err?.status === 409 && err?.detail?.error === 'job_running') {
        // A review batch is in flight: edits wait, questions are fine (WC-07).
        toast.warning('Pause the review to make other edits.');
        setState((prev) => ({
          ...prev,
          conversationHistory: prev.conversationHistory.filter((t) => t.id !== tempUserId && t.id !== tempAssistantId),
          }));
        return false; // not sent: the caller keeps the text
        }
      if (handleQuotaError(err)) {
        // popup shown
        } else if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('API key rejected. Refresh page.');
        } else {
        toast.error(String(err));
        }
      setState((prev) => ({ ...prev, error: String(err), loading: false }));
      }
    return true;
    };


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
    stopJobLoop();
    setState((prev) => ({
      ...prev,
      sessionId: sess.id,
      workingJson: (data.working_json as Record<string, any>) || payload.workingJson,
      baselineJson: (data.baseline_json as Record<string, any>) || payload.workingJson,
      versions: mapVersions(data.versions),
      conversationHistory: [],
      job: null,
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
    stopJobLoop();
    setState((prev) => ({
      ...prev,
      sessionId: sess.id,
      workingJson: {},
      baselineJson: {},
      versions: [],
      conversationHistory: [],
      job: null,
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

  // ── Whole-document review job (ADR-0026, WC-02..WC-08) ──────────────────

  const patchJob = (patch: Partial<JobUi>) =>
    setState((prev) => (prev.job ? { ...prev, job: { ...prev.job, ...patch } } : prev));

  // Countdown shown in the job panel; ends early when the user pauses.
  const jobCountdown = async (seconds: number, message: string) => {
    const until = Date.now() + seconds * 1000;
    patchJob({ wait: { message, reason: 'tokens', until }, current: null });
    while (Date.now() < until && !jobLoopRef.current.pause) {
      await new Promise((r) => setTimeout(r, 250));
      }
    patchJob({ wait: null });
    };

  // The client loop: one POST .../next per batch until the job is done,
  // paused or failed. Pausing never aborts a batch in flight — it stops
  // after it, so no model call is wasted.
  const runJobLoop = useCallback(async (sessionId: string, jobId: string) => {
    const loop = jobLoopRef.current;
    if (loop.active) return;
    loop.active = true;
    loop.pause = false;
    loop.cancel = false;
    patchJob({ phase: 'running', pausing: false, error: null, retryable: true });
    let end: JobPhase = 'paused';
    try {
      while (!loop.pause) {
        if (chatInFlightRef.current > 0) {
          patchJob({ current: 'Waiting for your chat message to finish…', wait: null });
          while (chatInFlightRef.current > 0 && !loop.pause) {
            await new Promise((r) => setTimeout(r, 500));
            }
          if (loop.pause) break;
          }
        patchJob({ inFlight: true, current: 'Preparing the next batch…', wait: null });
        let result: 'complete' | 'failed' | 'quota' | 'gone' | 'aborted' | 'none' = 'none';
        let finished = false;
        let retryIn = 0; // seconds; < 0 = do not retry automatically
        // Until the model call starts the batch only waits for capacity and
        // has reserved nothing: Pause/Cancel may abort it then (no tokens
        // spent). Once the call starts it always runs to the end.
        const abortCtrl = new AbortController();
        loop.abort = () => abortCtrl.abort();
        try {
          for await (const chunk of api.nextBatch(sessionId, jobId, apiKey, abortCtrl.signal)) {
            const d = chunk.data || {};
            if (chunk.type === 'progress' && (d.stage === 'calling' || d.stage === 'answering')) {
              loop.abort = null;
              }
            if (chunk.type === 'waiting') {
              patchJob({
                wait: {
                  message: d.message || 'Waiting for AI model capacity…',
                  reason: d.reason || 'tokens',
                  until: Date.now() + (Number(d.retry_after) || 0) * 1000,
                  },
                });
              } else if (chunk.type === 'progress' || chunk.type === 'retrying') {
              patchJob({ current: d.message || 'Working…', wait: null });
              } else if (chunk.type === 'batch_complete') {
              const done = d as api.BatchComplete;
              ReactDOM.flushSync(() => {
                setState((prev) => ({
                  ...prev,
                  workingJson: done.working_json || prev.workingJson,
                  conversationHistory: done.turn
                    ? [...prev.conversationHistory, done.turn as UiChatTurn]
                    : prev.conversationHistory,
                  job: prev.job ? { ...prev.job, job: done.job, error: null } : prev.job,
                  }));
                });
              result = 'complete';
              finished = done.job.status === 'done';
              } else if (chunk.type === 'batch_failed') {
              const failed = d as api.BatchFailed;
              patchJob({ job: failed.job, error: failed.error, retryable: failed.retryable !== false });
              result = 'failed';
              } else if (chunk.type === 'safety_block') {
              // Provider refused the content: retrying the same batch cannot help (WC-05).
              patchJob({ error: d.message || 'The AI provider refused this batch (content policy).', retryable: false });
              result = 'failed';
              } else if (chunk.type === 'credit_limit') {
              showRateLimitModal({ scope: d.scope || 'api', kind: 'credits', message: d.message, loginAvailable: d.login_available === true });
              patchJob({ error: d.message || 'The free credits are used up.' });
              result = 'quota';
              retryIn = -1;
              } else if (chunk.type === 'rate_limit') {
              result = 'quota';
              retryIn = Number(d.retry_after) || 30;
              }
            }
          } catch (err: any) {
          if (err?.userAborted) {
            result = 'aborted';
            } else if (err?.status === 429) {
            result = 'quota';
            retryIn = Number(err.retryAfter) || 15;
            } else if (err?.status === 402) {
            handleQuotaError(err);
            patchJob({ error: 'The free credits are used up.' });
            result = 'quota';
            retryIn = -1;
            } else if (err?.status === 409 && err?.detail?.error === 'job_running') {
            result = 'quota'; // another tab's batch is in flight
            retryIn = 5;
            } else if (err?.status === 409 || err?.status === 404) {
            result = 'gone'; // finished elsewhere, or lost with a backend restart
            } else {
            patchJob({ error: String(err?.message || err), retryable: true });
            result = 'failed';
            }
          }
        loop.abort = null;
        patchJob({ inFlight: false, current: null, wait: null });

        if (result === 'aborted') { end = 'paused'; break; }
        if (result === 'complete') {
          if (finished) { end = 'done'; break; }
          continue;
          }
        if (result === 'failed') { end = 'failed'; break; }
        if (result === 'quota') {
          if (retryIn < 0) { end = 'paused'; break; }
          await jobCountdown(retryIn, 'Request limit reached — continuing shortly');
          continue;
          }
        // 'gone' or a stream that ended without a result: ask the server.
        try {
          const job = await api.getJob(sessionId, jobId, apiKey);
          patchJob({ job });
          end = phaseOf(job);
          if (result === 'none' && end === 'paused') {
            patchJob({ error: 'The batch ended unexpectedly.', retryable: true });
            end = 'failed';
            }
          } catch {
          patchJob({ error: 'The review no longer exists on the server (it does not survive a backend restart).', retryable: false });
          end = 'cancelled';
          }
        break;
        }

      if (loop.cancel && end !== 'done' && end !== 'cancelled') {
        // After an abort the server notices the closed stream within a few
        // seconds; until then it answers 409 job_running.
        for (let attempt = 0; attempt < 12; attempt++) {
          try {
            const job = await api.cancelJob(sessionId, jobId, apiKey);
            patchJob({ job });
            end = 'cancelled';
            break;
            } catch (err: any) {
            if (err?.status === 409 && attempt < 11) { await new Promise((r) => setTimeout(r, 1000)); continue; }
            toast.error(String(err?.message || err));
            break;
            }
          }
        }
      } finally {
      loop.active = false;
      patchJob({ phase: end, inFlight: false, pausing: false, current: null, wait: null });
      }
    }, [apiKey]);

  const startJob = useCallback(async (proposal: api.JobProposal, sourceTurnId?: string) => {
    if (!state.sessionId) return;
    const sessionId = state.sessionId;
    try {
      const job = await api.createJob(sessionId, {
        scope_path: proposal.scope_path,
        instruction: proposal.instruction,
        source_turn_id: sourceTurnId ?? null,
        }, apiKey);
      setState((prev) => ({ ...prev, job: newJobUi(job, 'running') }));
      trackEvent('review_job_start');
      void runJobLoop(sessionId, job.id);
      } catch (err: any) {
      if (err?.status === 409 && err?.detail?.job_id) {
        // One active job per session: show the existing one instead.
        toast.warning('A review is already in progress for this document.');
        try {
          const job = await api.getJob(sessionId, err.detail.job_id, apiKey);
          setState((prev) => ({ ...prev, job: prev.job ?? newJobUi(job) }));
          } catch { /* ignore */ }
        } else if (!handleQuotaError(err)) {
        toast.error(String(err?.message || err));
        }
      }
    }, [state.sessionId, apiKey, runJobLoop]);

  const pauseJob = useCallback(() => {
    if (!jobLoopRef.current.active) return;
    jobLoopRef.current.pause = true;
    jobLoopRef.current.abort?.(); // only while still waiting for capacity
    patchJob({ pausing: true });
    }, []);

  const resumeJob = useCallback(() => {
    if (!state.sessionId || !state.job) return;
    void runJobLoop(state.sessionId, state.job.job.id);
    }, [state.sessionId, state.job, runJobLoop]);

  const cancelJob = useCallback(async () => {
    if (!state.sessionId || !state.job) return;
    const loop = jobLoopRef.current;
    if (loop.active) {
      // A batch is in flight: let it finish, then cancel (the loop does it).
      loop.cancel = true;
      loop.pause = true;
      loop.abort?.(); // only while still waiting for capacity
      patchJob({ pausing: true });
      return;
      }
    try {
      const job = await api.cancelJob(state.sessionId, state.job.job.id, apiKey);
      patchJob({ job, phase: 'cancelled', error: null });
      } catch (err: any) {
      if (err?.status === 404) { setState((prev) => ({ ...prev, job: null })); return; }
      toast.error(String(err?.message || err));
      }
    }, [state.sessionId, state.job, apiKey]);

  const dismissJob = useCallback(() => {
    if (jobLoopRef.current.active) return;
    setState((prev) => ({ ...prev, job: null }));
    }, []);

  const resolveJobBatch = async (fn: typeof api.acceptDiffBatch, jobId: string, batchNo: number) => {
    if (!state.sessionId) return;
    try {
      const data = await fn(state.sessionId, apiKey, { jobId, batchNo });
      setState((prev) => ({
        ...prev,
        workingJson: data.working_json,
        baselineJson: data.baseline_json || prev.baselineJson,
        conversationHistory: syncStatuses(prev.conversationHistory, data.conversation_history),
        }));
      } catch (err: any) { toast.error(String(err?.message || err)); }
    };
  const acceptJobBatch = useCallback((jobId: string, batchNo: number) =>
    resolveJobBatch(api.acceptDiffBatch, jobId, batchNo), [state.sessionId, apiKey]);
  const rejectJobBatch = useCallback((jobId: string, batchNo: number) =>
    resolveJobBatch(api.rejectDiffBatch, jobId, batchNo), [state.sessionId, apiKey]);

  // Tab refocus: re-read the job (another tab may have advanced or ended
  // it). Never starts the loop (WC-06).
  const jobId = state.job?.job.id ?? null;
  useEffect(() => {
    if (!jobId || !state.sessionId) return;
    const sessionId = state.sessionId;
    const onVisible = async () => {
      if (document.visibilityState !== 'visible' || jobLoopRef.current.active) return;
      try {
        const job = await api.getJob(sessionId, jobId, apiKey);
        setState((prev) => {
          if (!prev.job || prev.job.job.id !== job.id || jobLoopRef.current.active) return prev;
          const phase = job.status === 'done' || job.status === 'cancelled' ? phaseOf(job) : prev.job.phase;
          return { ...prev, job: { ...prev.job, job, phase } };
          });
        } catch { /* keep what we have */ }
      };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
    }, [jobId, state.sessionId, apiKey]);

  // Leaving while a batch is in flight wastes that model call (WC-08).
  const batchInFlight = !!state.job?.inFlight;
  useEffect(() => {
    if (!batchInFlight) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
    }, [batchInFlight]);

  const [unsavedChangesModalOpen, setUnsavedChangesModalOpen] = useState(false);
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);

  function deepEqual(a: any, b: any): boolean {
    return JSON.stringify(a) === JSON.stringify(b);
   }

  const callSelectVersion = async (versionId: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.selectVersion(state.sessionId, versionId, apiKey);
      stopJobLoop();
      setState({
          ...state,
        workingJson: data.working_json || {},
        baselineJson: data.baseline_json || {},
        conversationHistory: (data.conversation_history as UiChatTurn[]) || [],
        activeVersionId: data.active_version_id,
        job: null, // the backend cancels the review when the document is switched
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
      <SessionContext.Provider value={{ state, createSession, uploadJson, sendMessage, acceptDiff, createVersion, selectVersion, exportJson, removeDiff, acceptAllDiffs, rejectAllDiffs, refreshSession, explainJson, clearCache, loadSnapshot, clearSession, clearChat, startJob, pauseJob, resumeJob, cancelJob, dismissJob, acceptJobBatch, rejectJobBatch }}>
        {children}
      </SessionContext.Provider>
    );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
