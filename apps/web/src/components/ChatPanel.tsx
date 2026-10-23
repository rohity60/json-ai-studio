'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles, FileJson2, Brain, Eraser, CheckCircle2, XCircle, Clock, AlertTriangle } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { contextPairCount, diffStatus } from '@/lib/chatHistory';
import type { DiffEntry, DiffStatus } from '@/lib/api';
import { peekStarterPrompts, clearStarterPrompts } from '@/lib/openInWorkspace';
import { trackEvent } from '@/lib/gtagConversion';
import Button from '@/components/ui/Button';

// JSON-agnostic fallbacks — shown when no sample-specific prompts are wired
// in (e.g. user's own upload or a restored session), so they must make sense
// against any document. Edit-style only: the chat LLM produces diffs and
// refuses "explain" requests — explaining goes through the dedicated
// /api/explain flow (the Explain button on the preview panel).
const EXAMPLE_PROMPTS = [
  'Add a "description" field at the top',
    'Change content type to application/text for "Create item"',
  'Remove any empty or null values',
  'Rename service to orders-api',
  'remove all occurrences of timeout',
];

const STATUS_STYLE: Record<DiffStatus, { label: string; cls: string; Icon: typeof Clock }> = {
  pending: { label: 'Pending', cls: 'bg-amber-50 text-amber-700 border-amber-200', Icon: Clock },
  accepted: { label: 'Accepted', cls: 'bg-green-50 text-green-700 border-green-200', Icon: CheckCircle2 },
  rejected: { label: 'Rejected', cls: 'bg-gray-50 text-gray-500 border-gray-200 line-through', Icon: XCircle },
  failed: { label: "Couldn't apply", cls: 'bg-red-50 text-red-700 border-red-200', Icon: AlertTriangle },
};

// Per-diff status list inside an assistant bubble. Failed diffs collapse
// behind a summary so the thread stays readable.
function DiffStatusList({ diffs }: { diffs: DiffEntry[] }) {
  const [showFailed, setShowFailed] = useState(false);
  const applied = diffs.filter((d) => diffStatus(d) !== 'failed');
  const failed = diffs.filter((d) => diffStatus(d) === 'failed');
  const row = (d: DiffEntry) => {
    const st = STATUS_STYLE[diffStatus(d)];
    return (
      <li key={d.id} className="flex items-center gap-2 min-w-0" title={d.failure_reason || undefined}>
        <span className={`inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${st.cls}`}>
          <st.Icon className="w-3 h-3" />
          {st.label}
        </span>
        <span className="truncate font-mono text-[11px] text-gray-600">
          {d.operation} {d.path}
        </span>
      </li>
    );
  };
  return (
    <div className="mt-2 space-y-1">
      {applied.length > 0 && <ul className="space-y-1">{applied.map(row)}</ul>}
      {failed.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowFailed((v) => !v)}
            className="text-[11px] text-red-700 hover:underline"
          >
            {failed.length} change(s) couldn&apos;t be applied {showFailed ? '▴' : '▾'}
          </button>
          {showFailed && <ul className="mt-1 space-y-1">{failed.map(row)}</ul>}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({ onGoToUpload, onNewJson, suggestions }: {
  onGoToUpload?: () => void;
  onNewJson?: () => void;
  suggestions?: string[];
}) {
  const { state, sendMessage, clearChat } = useSession();
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [starterPrompts, setStarterPrompts] = useState<string[]>([]);
  const messagesRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const hasJson = Object.keys(state.workingJson || {}).length > 0;
  const contextPairs = contextPairCount(state.conversationHistory);

  // One-shot starter prompts stashed by an "Open in Workspace" click (ADR-0020).
  useEffect(() => {
    setStarterPrompts(peekStarterPrompts());
  }, []);

  // Scroll ONLY the messages list. scrollIntoView also scrolls ancestor
  // containers (overflow-hidden boxes scroll programmatically), which pushed
  // the Chat/Upload tab bar out of view once the history grew.
  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    }, [state.conversationHistory, isStreaming]);

  const send = async (message: string) => {
    if (!message.trim() || !state.sessionId || isStreaming || !hasJson) return;

    setInput('');
    setStarterPrompts([]);
    clearStarterPrompts();
    setIsStreaming(true);
    trackEvent('chat_submit');

    try {
      await sendMessage(message.trim(), thinking);
       } catch {
         // Message sent or failed - stop streaming
       } finally {
      setIsStreaming(false);
       }
     };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await send(input);
     };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
       }
     };

  return (
      <div className="flex flex-col h-full">
         <div className="border-b p-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-purple-600" />
          <h3 className="font-semibold">AI Chat</h3>
         <div className="ml-auto flex items-center gap-2 min-w-0">
           <span className="hidden sm:inline truncate text-xs text-muted-foreground">
             {state.sessionId ? `Session: ${state.sessionId.slice(0, 8)}` : 'No session'}
           </span>
           {state.conversationHistory.length > 0 && (
             <Button
              variant="secondary"
              onClick={() => clearChat()}
              disabled={isStreaming}
              title="Clear the conversation so the AI starts without earlier context"
             >
               <Eraser className="w-3.5 h-3.5" />
               Clear chat
             </Button>
           )}
           {onNewJson && hasJson && (
             <Button variant="secondary" onClick={onNewJson} title="Start over with a different JSON">
               <FileJson2 className="w-3.5 h-3.5" />
               New JSON
             </Button>
           )}
         </div>
         </div>

         <div ref={messagesRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {state.conversationHistory.length === 0 && !hasJson && (
             <div className="text-center text-muted-foreground mt-8 flex flex-col items-center gap-3">
              <FileJson2 className="w-10 h-10 text-gray-300" />
              <p className="text-sm">Upload a JSON file to get started</p>
              {onGoToUpload && (
                <Button variant="primary" onClick={onGoToUpload}>Upload JSON</Button>
              )}
             </div>
          )}

          {state.conversationHistory.length === 0 && hasJson && (
             <div className="text-center text-muted-foreground mt-8">
              <p className="text-sm mb-3">
                {starterPrompts.length > 0
                  ? 'Try one of these to get started'
                  : 'Send a message to start editing your JSON'}
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {(suggestions?.length
                  ? suggestions
                  : starterPrompts.length
                    ? starterPrompts
                    : EXAMPLE_PROMPTS
                ).map((prompt) => (
                  <Button
                    key={prompt}
                    variant="chip"
                    disabled={isStreaming}
                    onClick={() => send(prompt)}
                  >
                    {prompt}
                  </Button>
                ))}
              </div>
             </div>
          )}

         {state.conversationHistory.map((msg, i) => msg.kind === 'boundary' ? (
             <div key={msg.id || i} className="flex items-center gap-2 py-1 text-[11px] text-muted-foreground">
              <span className="h-px flex-1 bg-gray-200" />
              <span className="text-center">{msg.content} — earlier messages are not used as context</span>
              <span className="h-px flex-1 bg-gray-200" />
             </div>
          ) : (
             <div key={msg.id || i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-lg p-3 text-sm whitespace-pre-wrap break-words ${
                 msg.role === 'user'
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-100 border'
              }`}>
                {msg.role === 'assistant' && (
                   <div className="flex items-center gap-1 mb-1">
                    <Sparkles className="w-3 h-3" />
                    <span className="text-xs opacity-70">AI</span>
                   </div>
                )}
                {msg.content}
                {msg.role === 'assistant' && !!msg.diffs?.length && <DiffStatusList diffs={msg.diffs} />}
                {msg.role === 'assistant' && msg.question?.text && (
                  <div className="mt-2 space-y-1.5">
                    {!msg.content.includes(msg.question.text) && (
                      <p className="font-medium">{msg.question.text}</p>
                    )}
                    {/* Options are only actionable on the latest turn. */}
                    {i === state.conversationHistory.length - 1 && !!msg.question.options?.length && (
                      <div className="flex flex-wrap gap-1.5">
                        {msg.question.options.map((option) => (
                          <Button
                            key={option}
                            variant="chip"
                            disabled={isStreaming}
                            onClick={() => send(option)}
                          >
                            {option}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
             </div>
          ))}

         {isStreaming && (
             <div className="flex items-center gap-2 text-sm text-muted-foreground p-3">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Processing...</span>
             </div>
          )}

         </div>

         <form onSubmit={handleSubmit} className="border-t p-4">
           <div className="flex gap-2">
             <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={hasJson ? 'Describe your JSON changes...' : 'Upload JSON first to start chatting'}
              disabled={!state.sessionId || isStreaming || !hasJson}
              rows={2}
              className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
             />
             <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={!state.sessionId || isStreaming || !input.trim() || !hasJson}
              className="self-end"
             >
              <Send className="w-4 h-4" />
             </Button>
           </div>
           <div className="mt-2 flex items-center gap-3">
             <button
              type="button"
              role="switch"
              aria-checked={thinking}
              aria-label="Toggle extended thinking"
              onClick={() => setThinking((t) => !t)}
              disabled={!hasJson}
              title="Extended thinking makes the model reason harder for complex edits (slower)."
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                thinking
                  ? 'border-purple-500 bg-purple-50 text-purple-700'
                  : 'border-gray-300 bg-white text-gray-500 hover:text-gray-700'
              }`}
             >
              <Brain className="w-3.5 h-3.5" />
              Thinking {thinking ? 'On' : 'Off'}
             </button>
             {contextPairs > 0 && (
               <span className="text-[11px] text-muted-foreground" title="Earlier messages and what you accepted/rejected help the AI understand follow-ups">
                Using last {contextPairs} message{contextPairs === 1 ? '' : 's'} as context
               </span>
             )}
           </div>
         </form>
       </div>
     );
}
