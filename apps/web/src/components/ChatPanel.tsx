'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles, FileJson2 } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import Button from '@/components/ui/Button';

const EXAMPLE_PROMPTS = [
  'Increase timeout to 60',
  'Add a retryCount of 5',
  'Rename service to orders-api',
  'Remove the refund endpoint',
];

export default function ChatPanel({ onGoToUpload }: { onGoToUpload?: () => void }) {
  const { state, sendMessage } = useSession();
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const hasJson = Object.keys(state.workingJson || {}).length > 0;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [state.conversationHistory, isStreaming]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !state.sessionId || isStreaming || !hasJson) return;

    const message = input.trim();
    setInput('');
    setIsStreaming(true);

    try {
      await sendMessage(message);
       } catch {
         // Message sent or failed - stop streaming
       } finally {
      setIsStreaming(false);
       }
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
         <span className="ml-auto text-xs text-muted-foreground">
           {state.sessionId ? `Session: ${state.sessionId.slice(0, 8)}` : 'No session'}
         </span>
         </div>

         <div className="flex-1 overflow-y-auto p-4 space-y-3">
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
              <p className="text-sm mb-3">Send a message to start editing your JSON</p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <Button
                    key={prompt}
                    variant="chip"
                    onClick={() => { setInput(prompt); textareaRef.current?.focus(); }}
                  >
                    {prompt}
                  </Button>
                ))}
              </div>
             </div>
          )}

         {state.conversationHistory.map((msg, i) => (
             <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-lg p-3 text-sm ${
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
              </div>
             </div>
          ))}

         {isStreaming && (
             <div className="flex items-center gap-2 text-sm text-muted-foreground p-3">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Processing...</span>
             </div>
          )}

         <div ref={messagesEndRef} />
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
         </form>
       </div>
     );
}
