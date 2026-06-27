'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { toast } from 'sonner';
import * as api from '../lib/api';

type SessionState = {
  sessionId: string | null;
  workingJson: Record<string, any>;
  versions: Array<{ id: string; label: string; json_data: any }>;
  conversationHistory: Array<{ role: string; content: string; diffs?: any[]; explanation?: string }>;
  activeVersionId: string | null;
  loading: boolean;
  error: string | null;
};

type SessionContextValue = {
  state: SessionState;
  createSession: (name: string) => Promise<void>;
  uploadJson: (jsonData: Record<string, any>) => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  acceptDiff: (diffId: string) => Promise<void>;
  createVersion: (label: string) => void;
  selectVersion: (version: any) => void;
  exportJson: () => void;
  removeDiff: (diffId: string) => Promise<void>;
  acceptAllDiffs: () => Promise<void>;
  rejectAllDiffs: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);


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
    sessionId: null, workingJson: {}, versions: [],
    conversationHistory: [], activeVersionId: null,
    loading: true, error: null,
          });

          // Hydrate from localStorage + fetch session from backend
  useEffect(() => {
    if (!apiKey) return;
    const saved = localStorage.getItem('json-ai-studio-session');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
                  // Fetch full session state from backend
        api.getSession(parsed.sessionId, apiKey).then((data) => {
          setState({
            sessionId: parsed.sessionId,
            workingJson: (data.working_json as Record<string, any>) || {},
            versions: (data.versions || []).map((v: any) => ({
              id: v.id, label: v.label, json_data: v.json_data
                        })),
            conversationHistory: [],
            activeVersionId: null,
            loading: false,
            error: null,
                    });
                  }).catch(() => {
                    // Session load failed -- clear stale data & start fresh
              localStorage.removeItem('json-ai-studio-session');
              toast.warning('Session expired. Starting fresh.');
              setState((prev) => ({ ...prev, loading: false }));
                   });
                } catch {
        localStorage.removeItem('json-ai-studio-session');
               }
              } else {
                 // No saved session -- start fresh
        setState((prev) => ({ ...prev, loading: false }));
              }
            }, [apiKey]);

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
        versions: (data.versions || []).map((v: any) => ({
          id: v.id, label: v.label, json_data: v.json_data
               })),
        conversationHistory: [],
        loading: false,
        error: null,
             });
           } catch (err: any) {
      if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('Auth required. Refresh the page to get a new key.');
             } else if (err.message?.includes('429')) {
        toast.warning('Rate limited. Wait a moment before trying again.');
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
      setState((prev) => ({
             ...prev,
        sessionId: data.session_id || prev.sessionId,
        workingJson: data.parsed_json || prev.workingJson,
        error: null,
        loading: false,
            }));
            } catch (err: any) {
      if (err.message?.includes('401') || err.message?.includes('API key')) {
        toast.error('Auth required. Refresh page to get a new key.');
             } else if (err.message?.includes('429')) {
        toast.warning('Rate limited. Wait a moment before trying again.');
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
    const currentWorkingJson = state.workingJson;
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
        let structureChanged = false;

        if (chunk.type === 'diff' && chunk.data.entry) {
          diffs.push(chunk.data.entry);
          structureChanged = true;
           } else if (chunk.type === 'complete' && chunk.data.working_json) {
              // Capture the brand new JSON emitted from your API response
          activeJson = chunk.data.working_json;
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
                        workingJson: activeJson || prev.workingJson
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
        if (err.message?.includes('401') || err.message?.includes('API key')) {
          toast.error('API key rejected. Refresh page.');
           } else if (err.message?.includes('429')) {
          toast.warning('Rate limited. Wait before retrying.');
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
      setState(prev => ({ ...prev, workingJson: data.working_json }));
     } catch (err: any) { toast.error(String(err)); }
   }, [state.sessionId, apiKey]);

  const createVersion = useCallback(async ( label: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.createVersion(state.sessionId,label, apiKey);
      setState(prev => ({ ...prev, workingJson: data.working_json }));
     } catch (err: any) { toast.error(String(err)); }
   }, [state.sessionId, apiKey]);

  const removeDiff = useCallback(async (diffId: string) => {
    if (!state.sessionId) return;
    try {
      const data = await api.rejectDiff(state.sessionId, diffId, apiKey);
      setState(prev => ({ ...prev, workingJson: data.working_json }));
     } catch (err: any) { toast.error(String(err)); }
   }, [state.sessionId, apiKey]);

  const acceptAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.acceptDiffBatch(state.sessionId, apiKey);
      setState(prev => ({ ...prev, workingJson: data.working_json }));
     } catch (err: any) { toast.error(String(err)); }
   }, [state.sessionId, apiKey]);

  const rejectAllDiffs = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      const data = await api.rejectDiffBatch(state.sessionId, apiKey);
      setState(prev => ({ ...prev, workingJson: data.working_json }));
     } catch (err: any) { toast.error(String(err)); }
   }, [state.sessionId, apiKey]);


  const selectVersion = useCallback((version: any) => {
      setState((prev) => ({ ...prev, workingJson: version.json_data || {}, activeVersionId: version.id }));
           }, []);

  const exportJson = useCallback(() => {
    if (!state.sessionId) return;
            // build a data-URI blob for download
    const jsonStr = JSON.stringify(state.workingJson, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
           }, [state]);

         // Block UI until initial session data loaded from backend
  if (state.loading) return null;

  return (
            <SessionContext.Provider value={{ state, createSession, uploadJson, sendMessage, acceptDiff, createVersion, selectVersion, exportJson, removeDiff, acceptAllDiffs, rejectAllDiffs }}>
              {children}
            </SessionContext.Provider>
           );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}