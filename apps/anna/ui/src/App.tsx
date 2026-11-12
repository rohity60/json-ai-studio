// Studio shell for the Anna App. Same two-panel layout as the web studio
// (apps/web/src/app/studio/page.tsx) and the same components; the parts
// that depend on web-only features (login, workspaces, site navigation)
// are left out.
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Check, Code2, Copy, Download, FileJson2, History, MessageSquare, Plus, Sparkles } from 'lucide-react';

import ChatPanel from '@/components/ChatPanel';
import DiffViewer from '@/components/DiffViewer';
import ExplainPanel from '@/components/ExplainPanel';
import JSONTree from '@/components/JSONTree';
import Logo from '@/components/Logo';
import UploadPanel from '@/components/UploadPanel';
import Button from '@/components/ui/Button';
import { useSession } from '@/context/SessionContext';
import { pendingDiffs } from '@/lib/chatHistory';
import { SAMPLES, type Sample } from '@/lib/samples';

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

export default function App() {
  const {
    state, uploadJson, explainJson, exportJson, createVersion, selectVersion, clearSession,
  } = useSession();

  const json: Record<string, any> = state.workingJson || {};
  const hasJson = Object.keys(json).length > 0;
  const diffCount = pendingDiffs(state.conversationHistory).length;

  const [activeTab, setActiveTab] = useState<'chat' | 'upload'>(() => (hasJson ? 'chat' : 'upload'));
  const [previewTab, setPreviewTab] = useState<'preview' | 'diff'>('preview');
  const [copied, setCopied] = useState(false);
  const [savingVersion, setSavingVersion] = useState(false);
  const [versionLabel, setVersionLabel] = useState('');
  const [suggestions, setSuggestions] = useState<string[] | undefined>(undefined);

  // Open the Diff Viewer when a new assistant message carries pending diffs.
  const lastDiffMsgRef = useRef(-1);
  useEffect(() => {
    const idx = state.conversationHistory.length - 1;
    const last = state.conversationHistory[idx];
    const lastHasPending = (last?.diffs || []).some((d) => (d.status ?? 'pending') === 'pending');
    if (last?.role === 'assistant' && lastHasPending && idx !== lastDiffMsgRef.current) {
      lastDiffMsgRef.current = idx;
      setPreviewTab('diff');
    }
  }, [state.conversationHistory]);

  const handleUpload = async (data: Record<string, any>, prompts?: string[]) => {
    if (hasJson && !confirm('Replace the current JSON? Its chat and pending changes will be cleared.')) return;
    const ok = await uploadJson(data);
    if (ok) {
      setSuggestions(prompts);
      setActiveTab('chat');
      setPreviewTab('preview');
    }
  };

  const handleLoadSample = (sample: Sample) => handleUpload(sample.json, sample.prompts);

  const handleNewJson = async () => {
    if (hasJson && !confirm('Start a new JSON? Your current JSON stays saved in Anna, but this view will be cleared.')) return;
    await clearSession();
    setSuggestions(undefined);
    setPreviewTab('preview');
    setActiveTab('upload');
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(json, null, 2));
    setCopied(true);
    toast.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 1500);
  };

  const handleSaveVersion = () => {
    const label = versionLabel.trim();
    if (label) {
      createVersion(label);
      toast.success(`Version "${label}" saved`);
    }
    setVersionLabel('');
    setSavingVersion(false);
  };

  const handleSelectVersion = async (versionId: string) => {
    if (!versionId) return;
    if (diffCount > 0 && !confirm('Loading a version discards the pending changes. Continue?')) return;
    await selectVersion(versionId);
    setPreviewTab('preview');
  };

  return (
    <div className="h-screen h-dvh flex flex-col">
      <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
        <Logo />
        <Button variant="primary" onClick={handleNewJson} title="Start over with a different JSON">
          <Plus className="w-4 h-4" />
          New JSON
        </Button>
      </header>

      <main className="flex flex-1 min-h-0 flex-col md:flex-row">
        {/* Left: chat and upload */}
        <div className="w-full md:w-[420px] border-b md:border-b-0 md:border-r flex flex-col h-[45dvh] shrink-0 md:h-auto md:shrink min-h-0 overflow-hidden">
          <div className="flex border-b">
            <TabButton active={activeTab === 'chat'} onClick={() => setActiveTab('chat')}>
              <MessageSquare className="w-4 h-4 inline mr-1" />Chat
            </TabButton>
            <TabButton active={activeTab === 'upload'} onClick={() => setActiveTab('upload')}>
              <Code2 className="w-4 h-4 inline mr-1" />Upload
            </TabButton>
          </div>
          {activeTab === 'chat' && (
            <div className="flex-1 min-h-0 flex flex-col">
              <ChatPanel
                onGoToUpload={() => setActiveTab('upload')}
                onNewJson={handleNewJson}
                suggestions={suggestions}
              />
            </div>
          )}
          {activeTab === 'upload' && (
            <div className="p-4 flex-1 overflow-y-auto">
              <UploadPanel onUpload={handleUpload} onLoadSample={handleLoadSample} />
            </div>
          )}
        </div>

        {/* Right: working JSON and diff */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
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
            <div className="flex items-center gap-3 flex-wrap min-w-0">
              <span className="text-xs text-gray-500">
                {hasJson ? `${Object.keys(json).length} keys` : 'Empty'}
              </span>
              {state.versions.length > 0 && (
                <label className="flex items-center gap-1 text-xs text-gray-600">
                  <History className="w-4 h-4" />
                  <select
                    aria-label="Load a saved version"
                    className="rounded-lg border px-2 py-1 text-sm"
                    value={state.activeVersionId ?? ''}
                    onChange={(e) => handleSelectVersion(e.target.value)}
                  >
                    <option value="">Versions ({state.versions.length})</option>
                    {state.versions.map((v) => (
                      <option key={v.id} value={v.id}>{v.label || v.id}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>

          <div className="flex-1 p-4 overflow-auto">
            {previewTab === 'preview' && (hasJson ? (
              <>
                <JSONTree data={json} name="Working JSON" />
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
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveVersion();
                          if (e.key === 'Escape') { setVersionLabel(''); setSavingVersion(false); }
                        }}
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
                </div>
                {(state.explaining || state.explainError || state.explainMarkdown) && (
                  <ExplainPanel
                    markdown={state.explainMarkdown || ''}
                    onRetry={() => explainJson()}
                    loading={state.explaining}
                    error={state.explainError}
                  />
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center min-h-full gap-6 py-6">
                <div className="text-center max-w-md">
                  <Sparkles className="w-8 h-8 mx-auto text-purple-500" />
                  <h3 className="mt-3 text-lg font-semibold">Try it in one click</h3>
                  <p className="mt-1 text-sm text-gray-500">
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
                      <p className="mt-1.5 text-xs text-gray-500">{s.description}</p>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500">…or upload / paste your own JSON in the Upload tab</p>
              </div>
            ))}
            {previewTab === 'diff' && (hasJson ? (
              <DiffViewer before={state.baselineJson} after={json} onResolved={() => setPreviewTab('preview')} />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">No diff data available</div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
