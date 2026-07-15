'use client';

import { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import UploadPanel from '@/components/UploadPanel';
import ChatPanel from '@/components/ChatPanel';
import DiffViewer from '@/components/DiffViewer';
import JSONTree from '@/components/JSONTree';
import WorkspaceSidebar from '@/components/WorkspaceSidebar';
import { useSession } from '@/context/SessionContext';
import { useWorkspace } from '@/context/WorkspaceContext';
import { FileJson2, MessageSquare, Code2, History, Sparkles, Download, Copy, Check, Plus, Save } from 'lucide-react';
import ExplainPanel from '@/components/ExplainPanel';
import Logo from '@/components/Logo';
import UserChip from '@/components/UserChip';
import Button from '@/components/ui/Button';
import WorkspaceSwitcher from '@/components/WorkspaceSwitcher';
import StatusPill from '@/components/StatusPill';
import { showSaveDialog } from '@/components/SaveDialog';
import { showRateLimitModal } from '@/components/RateLimitModal';
import { SAMPLES, getSample, type Sample } from '@/lib/samples';

// Left-panel tab (Chat / Upload): underline style, full width
function TabButton({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
        active ? 'border-purple-600 text-purple-600' : 'border-transparent'
      }`}
    >
      {children}
    </button>
  );
}

// Pending diffs live on the latest assistant message (same source DiffViewer reads)
function pendingDiffCount(history: Array<{ role: string; diffs?: any[] }>): number {
  for (let i = history.length - 1; i >= 0; i--) {
    const turn = history[i];
    if (turn.role === 'assistant' && turn.diffs?.length) return turn.diffs.length;
  }
  return 0;
}

export default function Home() {
  const { state, createSession, uploadJson, explainJson, exportJson, createVersion } = useSession();
  const { dirty, loggedIn, guardDirty } = useWorkspace();

  // SessionProvider blocks render until hydration, so workingJson is final here
  const [activeTab, setActiveTab] = useState<'chat' | 'upload'>(
    () => (Object.keys(state.workingJson || {}).length > 0 ? 'chat' : 'upload')
  );
  const [previewTab, setPreviewTab] = useState<'preview' | 'diff'>('preview');
  const [showSidebar, setShowSidebar] = useState(false);
  const [copied, setCopied] = useState(false);
  const [savingVersion, setSavingVersion] = useState(false);
  const [versionLabel, setVersionLabel] = useState('');
  // Chat suggestion chips tailored to the loaded sample (undefined → generic defaults)
  const [sampleSuggestions, setSampleSuggestions] = useState<string[] | undefined>(undefined);

   // Derive displayed json from context workingJson.
   // On first mount workingJson is {} — fall back to an empty object.
  const json: Record<string, any> = state.workingJson || {};
  const diffCount = pendingDiffCount(state.conversationHistory);

  // Auto-open the Diff Viewer when a new assistant message carries diffs.
  // Ref guard: accepts/rejects mutate history without adding messages and
  // must not force the tab back.
  const lastDiffMsgRef = useRef(-1);
  useEffect(() => {
    const idx = state.conversationHistory.length - 1;
    const last = state.conversationHistory[idx];
    if (last?.role === 'assistant' && last.diffs?.length && idx !== lastDiffMsgRef.current) {
      lastDiffMsgRef.current = idx;
      setPreviewTab('diff');
    }
  }, [state.conversationHistory]);

  // Warn on tab close while workspace-unsaved changes exist (F6/U-06).
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  const handleUpload = async (data: Record<string, any>, prompts?: string[]) => {
     // Do NOT call createSession here — the upload endpoint already creates or reuses a session.
     // Calling createSession('My Config') spawns a fresh empty session that overwrites
     // the working_json, causing the UI to blank out immediately after upload succeeds.

     // Anonymous with a JSON already loaded: a 2nd JSON needs an account to
     // live in (req 7 / F5) — show the login CTA instead of replacing.
    if (!loggedIn && Object.keys(state.workingJson || {}).length > 0) {
      showRateLimitModal({ scope: 'api', kind: 'login' });
      return;
    }
     // Logged-in: replacing the working JSON drops unsaved work — guard it.
    if (loggedIn && !(await guardDirty())) return;
    const ok = await uploadJson(data);
    if (ok) {
      setSampleSuggestions(prompts);
      setActiveTab('chat');
      setPreviewTab('preview');
    }
   };

  const handleLoadSample = (sample: Sample) => handleUpload(sample.json, sample.prompts);

  // Deep link from the landing page: /studio?sample=<id> loads a built-in
  // sample on first visit so there is zero-friction between "Try it" and a
  // populated workspace. Never clobbers an existing working JSON.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('sample');
    if (!id) return;
    // Strip the param so refresh/back doesn't re-trigger the load.
    window.history.replaceState(null, '', window.location.pathname);
    const sample = getSample(id);
    if (!sample || Object.keys(state.workingJson || {}).length > 0) return;
    handleLoadSample(sample);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSaveToWorkspace = () => {
    if (!loggedIn) {
      showRateLimitModal({ scope: 'api', kind: 'login' });
      return;
    }
    showSaveDialog();
   };

  const handleNewSession = async () => {
    if (loggedIn && !(await guardDirty())) return;
    createSession('My Config');
   };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(json, null, 2));
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 1500);
   };

  const handleSaveVersion = () => {
    if (versionLabel.trim()) {
      createVersion(versionLabel.trim());
      toast.success(`Version "${versionLabel.trim()}" saved`);
    }
    setVersionLabel('');
    setSavingVersion(false);
   };

  return (
      <div className="h-screen h-dvh flex flex-col">
        {/* Header */}
        <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-2">
            {Object.keys(json).length === 0 && (
              <Button variant="primary" onClick={handleNewSession}>New Session</Button>
            )}
            <UserChip />
          </div>
        </header>

        {/* Stacks vertically on phones (chat on top, JSON below); side-by-side from md up */}
        <main className="flex flex-1 min-h-0 flex-col md:flex-row">
          {/* Left Panel - Chat & Upload */}
          <div className="w-full md:w-[420px] border-b md:border-b-0 md:border-r flex flex-col h-[45dvh] shrink-0 md:h-auto md:shrink">
            <div className="flex border-b">
              <TabButton active={activeTab === 'chat'} onClick={() => setActiveTab('chat')}>
                <MessageSquare className="w-4 h-4 inline mr-1" />Chat
              </TabButton>
              <TabButton active={activeTab === 'upload'} onClick={() => setActiveTab('upload')}>
                <Code2 className="w-4 h-4 inline mr-1" />Upload
              </TabButton>
            </div>

            {activeTab === 'chat' && (
              <ChatPanel onGoToUpload={() => setActiveTab('upload')} suggestions={sampleSuggestions} />
            )}
            {activeTab === 'upload' && (
              <div className="p-4 flex-1 overflow-y-auto">
                <UploadPanel onUpload={handleUpload} onLoadSample={handleLoadSample} />
              </div>
            )}
          </div>

          {/* Right Panel - JSON Preview / Diff */}
          <div className="flex-1 flex flex-col min-w-0 min-h-0">
            {/* Tab Bar */}
            <div className="flex items-center justify-between border-b px-4 py-2 flex-wrap gap-2">
              <div className="flex gap-2">
                <Button variant="pill" active={previewTab === 'preview'} onClick={() => setPreviewTab('preview')}>
                  Working JSON
                </Button>
                <Button variant="pill" active={previewTab === 'diff'} onClick={() => setPreviewTab('diff')}>
                  Diff Viewer
                  {diffCount > 0 && (
                    <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-purple-600 text-white text-[10px] font-semibold">
                      {diffCount}
                    </span>
                  )}
                </Button>
              </div>
              <div className="flex items-center gap-2 sm:gap-3 flex-wrap min-w-0">
                <span className="text-xs text-muted-foreground">
                  {Object.keys(json).length > 0 ? `${Object.keys(json).length} keys` : 'Empty'}
                </span>
                <StatusPill hasJson={Object.keys(json).length > 0} />
                <WorkspaceSwitcher />
                {!showSidebar && (
                  <Button variant="secondary" onClick={() => setShowSidebar(true)} title="Workspace JSONs + versions">
                    <History className="w-4 h-4" />
                    Workspace
                  </Button>
                )}
              </div>
            </div>

            {/* Tab Content */}
            <div className="flex-1 p-4 overflow-auto">
              {previewTab === 'preview' && (
              Object.keys(json).length > 0
                  ? <>
                      <JSONTree data={json} name="Working JSON" />
                      {Object.keys(json).length > 0 && (
                        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                          <Button variant="primary" onClick={() => explainJson()} disabled={state.explaining}>
                            <Sparkles className="w-4 h-4" />
                            {state.explaining ? 'Explaining...' : 'Explain'}
                          </Button>
                          <Button variant="secondary" onClick={handleCopy} title="Copy JSON to clipboard">
                            {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                            {copied ? 'Copied' : 'Copy'}
                          </Button>
                          <Button variant="secondary" onClick={() => exportJson()} title="Download as .json file">
                            <Download className="w-4 h-4" />
                            Download
                          </Button>
                          {savingVersion ? (
                            <span className="flex items-center gap-1">
                              <input
                                autoFocus
                                placeholder="Version label..."
                                value={versionLabel}
                                onChange={(e) => setVersionLabel(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleSaveVersion(); if (e.key === 'Escape') { setVersionLabel(''); setSavingVersion(false); } }}
                                className="px-3 py-1.5 text-sm rounded-lg border w-40 focus:outline-none focus:ring-2 focus:ring-purple-500"
                              />
                              <Button variant="primary" onClick={handleSaveVersion} disabled={!versionLabel.trim()}>
                                Save
                              </Button>
                              <Button variant="secondary" onClick={() => { setVersionLabel(''); setSavingVersion(false); }}>
                                Cancel
                              </Button>
                            </span>
                          ) : (
                            <Button variant="secondary" onClick={() => setSavingVersion(true)} title="Snapshot the current JSON as a version">
                              <Plus className="w-4 h-4" />
                              New Version
                            </Button>
                          )}
                          <Button variant="secondary" onClick={handleSaveToWorkspace} title="Save a copy as a new JSON (or into another workspace)">
                            <Save className="w-4 h-4" />
                            Save as…
                          </Button>
                        </div>
                      )}
                      {(state.explaining || state.explainError || state.explainMarkdown) && (
                        <ExplainPanel
                          markdown={state.explainMarkdown || ''}
                          onRetry={() => explainJson()}
                          loading={state.explaining}
                          error={state.explainError}
                        />
                      )}
                    </>
                  : <div className="flex flex-col items-center justify-center min-h-full gap-6 py-6">
                      <div className="text-center max-w-md">
                        <Sparkles className="w-8 h-8 mx-auto text-purple-500" />
                        <h3 className="mt-3 text-lg font-semibold">Try it in one click</h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Pick a sample, edit it with plain English, review the diff, download valid JSON.
                        </p>
                      </div>
                      <div className="grid w-full max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {SAMPLES.map((s) => (
                          <button
                            key={s.id}
                            onClick={() => handleLoadSample(s)}
                            className="rounded-xl border bg-white p-4 text-left transition hover:border-purple-300 hover:shadow-sm"
                          >
                            <div className="flex items-center gap-2">
                              <FileJson2 className="w-4 h-4 text-purple-600 shrink-0" />
                              <span className="text-sm font-semibold">{s.label}</span>
                            </div>
                            <p className="mt-1.5 text-xs text-muted-foreground">{s.description}</p>
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        …or upload / paste your own JSON in the Upload tab
                      </p>
                    </div>
              )}
              {previewTab === 'diff' && (
              Object.keys(json).length > 0
                  ? <DiffViewer before={state.baselineJson} after={json} onResolved={() => setPreviewTab('preview')} />
                  : <div className="flex items-center justify-center h-full text-muted-foreground">No diff data available</div>
              )}

            </div>
          </div>

          {/* Right Sidebar - workspace JSONs + version history (collapsible) */}
          {showSidebar && (
            <aside className="w-[280px] border-l hidden lg:flex lg:flex-col bg-gray-50">
              <div className="flex-1 min-h-0 overflow-y-auto">
                <WorkspaceSidebar onClose={() => setShowSidebar(false)} />
              </div>
            </aside>
          )}
        </main>
      </div>
    );
}
