'use client';

import { useState, useCallback } from 'react';
import UploadPanel from '@/components/UploadPanel';
import ChatPanel from '@/components/ChatPanel';
import DiffViewer from '@/components/DiffViewer';
import JSONTree from '@/components/JSONTree';
import VersionSidebar from '@/components/VersionSidebar';
import { useSession } from '@/context/SessionContext';
import { FileJson2, MessageSquare, Code2, LayoutList } from 'lucide-react';

export default function Home() {
  const { state, createSession, uploadJson } = useSession();
 
  const [activeTab, setActiveTab] = useState<'chat' | 'upload'>('chat');
  const [previewTab, setPreviewTab] = useState<'preview' | 'diff'>('preview');
  const [showSidebar, setShowSidebar] = useState(false);

   // Derive displayed json from context workingJson.
   // On first mount workingJson is {} — fall back to an empty object.
  const json: Record<string, any> = state.workingJson || {};

  const handleUpload = async (data: Record<string, any>) => {
    try {
      await uploadJson(data);
      } catch {}
     // Do NOT call createSession here — the upload endpoint already creates or reuses a session.
     // Calling createSession('My Config') spawns a fresh empty session that overwrites
     // the working_json, causing the UI to blank out immediately after upload succeeds.
    setActiveTab('chat');
   };

  return (
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileJson2 className="w-6 h-6 text-purple-600" />
            <div className="logo-container opt-1">
              <span className="brand-main">JSON</span>
              <span className="brand-sub-1">AI</span>
              <span className="brand-sub-2">STUDIO</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {Object.keys(json).length === 0 && (<button onClick={() => createSession('My Config')}
              className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700">
              New Session</button>
            )}
            <button onClick={() => setShowSidebar(!showSidebar)}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="Toggle sidebar">
              <LayoutList className="w-5 h-5" />
            </button>
          </div>
        </header>

        <main className="flex flex-1 min-h-0">
          {/* Left Panel - Chat & Upload */}
          <div className="w-[420px] border-r flex flex-col">
            <div className="flex border-b">
              <button onClick={() => setActiveTab('chat')}
              className={`flex-1 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'chat' ? 'border-purple-600 text-purple-600' : 'border-transparent'}`}>
                <MessageSquare className="w-4 h-4 inline mr-1" />Chat</button>
              <button onClick={() => setActiveTab('upload')}
              className={`flex-1 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'upload' ? 'border-purple-600 text-purple-600' : 'border-transparent'}`}>
                <Code2 className="w-4 h-4 inline mr-1" />Upload</button>
            </div>

            {activeTab === 'chat' && <ChatPanel />}
            {activeTab === 'upload' && (
              <div className="p-4 flex-1 overflow-y-auto">
                <UploadPanel onUpload={handleUpload} />
              </div>
            )}
          </div>

          {/* Right Panel - JSON Preview / Diff */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Tab Bar */}
            <div className="flex items-center justify-between border-b px-4 py-2">
              <div className="flex gap-2">
                <button onClick={() => setPreviewTab('preview')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  previewTab === 'preview' ? 'bg-purple-100 text-purple-700' : 'hover:bg-gray-100'}`}>
                 Working JSON</button>
                <button onClick={() => setPreviewTab('diff')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  previewTab === 'diff' ? 'bg-purple-100 text-purple-700' : 'hover:bg-gray-100'}`}>
                 Diff Viewer</button>
              </div>
              <span className="text-xs text-muted-foreground">
                {Object.keys(json).length > 0 ? `${Object.keys(json).length} keys` : 'Empty'}
              </span>
            </div>

            {/* Tab Content */}
            <div className="flex-1 p-4 overflow-auto">
              {previewTab === 'preview' && (
              json
                  ? <JSONTree data={json} name="Working JSON" />
                  : <div className="flex items-center justify-center h-full text-muted-foreground flex-col gap-4">
                      <FileJson2 className="w-16 h-16 text-gray-300" />
                      <p className="text-sm text-center">Upload a JSON file or use AI chat to start</p>
                    </div>
              )}
              {previewTab === 'diff' && (
              json
                  ? <DiffViewer before={state.baselineJson} after={json} />
                  : <div className="flex items-center justify-center h-full text-muted-foreground">No diff data available</div>
              )}
            </div>
          </div>

          {/* Right Sidebar - Version History (collapsible) */}
          {showSidebar && (
            <aside className="w-[280px] border-l hidden lg:block bg-gray-50">
              <VersionSidebar />
            </aside>
          )}
        </main>
      </div>
    );
}
