'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles, FileJson2, Brain, Eraser, CheckCircle2, XCircle, Clock, AlertTriangle, Hourglass, RotateCw, Play } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { contextPairCount, diffStatus, isFailedTurn } from '@/lib/chatHistory';
import type { DiffEntry, DiffStatus } from '@/lib/api';
import { peekStarterPrompts, clearStarterPrompts } from '@/lib/openInWorkspace';
import { trackEvent } from '@/lib/gtagConversion';
import Button from '@/components/ui/Button';
import { formatDuration, type TurnProgress } from '@/lib/progress';
import JobProposalCard from '@/components/JobProposalCard';
import JobPanel from '@/components/JobPanel';
import { isActivePhase } from '@/lib/reviewJob';

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
      <li key={d.id} className="min-w-0" title={d.failure_reason || undefined}>
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium ${st.cls}`}>
            <st.Icon className="w-3 h-3" />
            {st.label}
          </span>
          <span className="truncate font-mono text-[11px] text-gray-600" title={d.path}>
            {d.operation} {d.path}
          </span>
        </div>
        {/* Failed diffs: say why inline — a tooltip is invisible on touch
            and was the only place the edit-guard reason showed. */}
        {diffStatus(d) === 'failed' && d.failure_reason && (
          <p className="ml-1 mt-0.5 text-[11px] text-red-700 break-words">{d.failure_reason}</p>
        )}
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

// Ticks every second while `active` (client-side countdown; the server only
// re-sends `waiting` every 5 s).
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

const WAIT_HINT: Record<string, string> = {
  pacing: 'pacing',
  tokens: 'model limit',
  cooldown: 'cooldown',
};

// Turn progress inside the assistant bubble (PRD B §8, WB-08..11): plan,
// step X/N with a bar, live wait countdown, finished lookups and retries.
// Collapses to a one-line summary once the answer arrives.
function TurnProgressPanel({ progress, finished, failed = false }: { progress: TurnProgress; finished: boolean; failed?: boolean }) {
  const [open, setOpen] = useState(false);
  const now = useNow(!finished && !!progress.wait);
  const multiStep = (progress.steps ?? 1) > 1 || progress.done.length > 0;

  if (finished) {
    if (!multiStep) return null;
    const took = formatDuration((progress.finishedAt ?? now) - progress.startedAt);
    const lookups = progress.done.filter((l) => l.kind === 'tool').length;
    return (
      <div className="mt-2 text-[11px] text-gray-500 whitespace-normal">
        <button type="button" className="hover:underline" onClick={() => setOpen((v) => !v)}>
          {failed ? 'Stopped after' : 'Done in'} {took} · {lookups} lookup{lookups === 1 ? '' : 's'} {open ? '▴' : '▾'}
        </button>
        {open && <ProgressLines progress={progress} />}
      </div>
    );
  }

  const secs = progress.wait ? Math.max(0, Math.ceil((progress.wait.until - now) / 1000)) : 0;
  const pct = progress.step && progress.steps ? Math.min(100, Math.round(((progress.step - 1) / progress.steps) * 100)) : 0;
  return (
    <div className="space-y-1.5 whitespace-normal" aria-live="polite">
      {progress.plan && <p className="text-[11px] text-gray-500">{progress.plan}</p>}
      {(progress.current || progress.wait) && (
        <div className="flex items-center gap-1.5 text-xs text-gray-700">
          <Loader2 className="w-3 h-3 shrink-0 animate-spin" />
          <span>{progress.current ?? (progress.step && progress.steps ? `Step ${progress.step}/${progress.steps}` : 'Working…')}</span>
        </div>
      )}
      {!!progress.steps && progress.steps > 1 && (
        <div className="h-1 w-full rounded bg-gray-200 overflow-hidden">
          <div className="h-full bg-purple-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      {progress.wait && (
        <div className={`flex items-center gap-1.5 text-xs ${progress.wait.reason === 'cooldown' ? 'text-amber-700' : 'text-gray-600'}`}>
          <Hourglass className="w-3 h-3 shrink-0" />
          <span>
            {progress.wait.message} · {secs}s
            <span className="ml-1 text-[10px] opacity-70">({WAIT_HINT[progress.wait.reason] ?? 'waiting'})</span>
          </span>
        </div>
      )}
      <ProgressLines progress={progress} max={4} />
    </div>
  );
}

function ProgressLines({ progress, max }: { progress: TurnProgress; max?: number }) {
  const lines = max ? progress.done.slice(-max) : progress.done;
  if (!lines.length) return null;
  const hidden = progress.done.length - lines.length;
  return (
    <ul className="mt-1 space-y-0.5 text-[11px]">
      {hidden > 0 && <li className="text-gray-400">+{hidden} earlier step{hidden === 1 ? '' : 's'}</li>}
      {lines.map((l, i) => (
        <li key={i} className={`flex items-start gap-1.5 ${l.kind === 'retry' ? 'text-amber-700' : 'text-gray-600'}`}>
          {l.kind === 'retry'
            ? <RotateCw className="w-3 h-3 mt-0.5 shrink-0" />
            : <CheckCircle2 className="w-3 h-3 mt-0.5 shrink-0 text-green-600" />}
          <span className="break-words">{l.text}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ChatPanel({ onGoToUpload, onNewJson, suggestions }: {
  onGoToUpload?: () => void;
  onNewJson?: () => void;
  suggestions?: string[];
}) {
  const { state, sendMessage, resumeTurn, clearChat, startJob } = useSession();
  const jobActive = !!state.job && isActivePhase(state.job.phase);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [starterPrompts, setStarterPrompts] = useState<string[]>([]);
  // Proposal cards the user dismissed (by turn id); the turn text stays.
  const [dismissedProposals, setDismissedProposals] = useState<Set<string>>(new Set());
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
      const sent = await sendMessage(message.trim(), thinking);
      if (!sent) setInput(message); // refused (review batch running): keep the text
       } catch {
         // Message sent or failed - stop streaming
       } finally {
      setIsStreaming(false);
       }
     };

  // Continue the latest failed turn (ADR-0028, WB-02/03).
  const continueTurn = async (turnId: string) => {
    if (isStreaming || jobActive) return;
    setIsStreaming(true);
    trackEvent('chat_continue');
    try {
      await resumeTurn(turnId, thinking);
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
          ) : msg.kind === 'job_batch' ? (
             // One finished review batch (ADR-0026): a compact line; its
             // diffs are resolved per batch in the diff viewer.
             <div key={msg.id || i} className="flex items-center gap-1.5 px-1 text-[11px] text-gray-500" data-testid="job-batch-line">
              <CheckCircle2 className="w-3 h-3 shrink-0 text-green-600" />
              <span>{msg.content}</span>
             </div>
          ) : (
             <div key={msg.id || i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                data-testid={isFailedTurn(msg) ? 'failed-turn' : undefined}
                className={`max-w-[80%] rounded-lg p-3 text-sm whitespace-pre-wrap break-words ${
                 msg.role === 'user'
                  ? 'bg-purple-600 text-white'
                  : isFailedTurn(msg)
                    ? 'bg-gray-50 border border-dashed text-gray-500'
                    : 'bg-gray-100 border'
              }`}>
                {msg.role === 'assistant' && (
                   <div className="flex items-center gap-1 mb-1">
                    <Sparkles className="w-3 h-3" />
                    <span className="text-xs opacity-70">AI</span>
                    {isFailedTurn(msg) && (
                      <span className="ml-1 inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                        <AlertTriangle className="w-3 h-3" />
                        {msg.status === 'interrupted' ? 'Attempt interrupted' : 'Attempt failed'}
                      </span>
                    )}
                   </div>
                )}
                {msg.role === 'assistant' && msg.progress?.structured && !msg.content && (
                  <TurnProgressPanel progress={msg.progress} finished={false} />
                )}
                {msg.content}
                {msg.role === 'assistant' && msg.progress?.structured && !!msg.content && (
                  <TurnProgressPanel progress={msg.progress} finished failed={isFailedTurn(msg)} />
                )}
                {msg.role === 'assistant' && !!msg.diffs?.length && <DiffStatusList diffs={msg.diffs} />}
                {isFailedTurn(msg) && !!msg.read_paths?.length && (
                  <p className="mt-1.5 text-[11px] text-gray-500 whitespace-normal">
                    Already read: <span className="font-mono">{msg.read_paths.slice(0, 6).join(', ')}{msg.read_paths.length > 6 ? ` +${msg.read_paths.length - 6} more` : ''}</span>
                  </p>
                )}
                {/* Continue: latest failed turn only, while the server still
                    holds its trace (WB-02/03/07). */}
                {isFailedTurn(msg) && i === state.conversationHistory.length - 1 && !msg.ephemeral && !msg.resumeGone && (
                  <div className="mt-2">
                    <Button
                      variant="secondary"
                      disabled={isStreaming || jobActive}
                      onClick={() => continueTurn(msg.id)}
                      title="Pick up where this attempt stopped, without redoing the lookups it already made"
                      data-testid="continue-turn"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Continue
                    </Button>
                  </div>
                )}
                {msg.role === 'assistant' && msg.job_proposal && !dismissedProposals.has(msg.id) && (
                  state.job?.job.source_turn_id === msg.id ? (
                    <p className="mt-2 text-[11px] text-purple-700">Review started — follow it in the panel below.</p>
                  ) : (
                    <JobProposalCard
                      proposal={msg.job_proposal}
                      disabled={jobActive || !!msg.ephemeral}
                      onStart={() => startJob(msg.job_proposal!, msg.id)}
                      onDismiss={() => setDismissedProposals((prev) => new Set(prev).add(msg.id))}
                    />
                  )
                )}
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

         <JobPanel />

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
