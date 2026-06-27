'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Sparkles } from 'lucide-react';
import { useSession } from '@/context/SessionContext';

export default function ChatPanel() {
  const { state, sendMessage } = useSession();
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [state.conversationHistory, isStreaming]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log('[ChatPanel] handleSubmit called, inputLen:', input.length, 'sessionId:', state.sessionId, 'isStreaming:', isStreaming);
    if (!input.trim() || !state.sessionId || isStreaming) {
      console.warn('[ChatPanel] handleSubmit blocked: inputEmpty=', !input.trim(), 'noSession=', !state.sessionId, 'alreadyStreaming=', isStreaming);
      return;
     }

    const message = input.trim();
    console.log('[ChatPanel] Message captured:', message.slice(0, 100));
    setInput('');
    setIsStreaming(true);
    console.log('[ChatPanel] Input cleared, streaming=true');

    try {
      console.log('[ChatPanel] Calling sendMessage...');
      await sendMessage(message);
      console.log('[ChatPanel] sendMessage resolved successfully');
       } catch (err: any) {
        console.error('[ChatPanel] sendMessage threw:', err?.message || String(err));
         // Message sent or failed - stop streaming
       } finally {
      setIsStreaming(false);
      console.log('[ChatPanel] streaming=false, totalDurationMs:', performance.now().toFixed(0));
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
          {state.conversationHistory.length === 0 && (
             <div className="text-center text-muted-foreground mt-8">
              <p className="text-sm mb-2">Send a message to start editing your JSON</p>
              <p className="text-xs opacity-60">Examples: "Increase timeout to 60", "Add retry count"</p>
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
              placeholder="Describe your JSON changes..."
              disabled={!state.sessionId || isStreaming}
              rows={2}
              className="flex-1 resize-none rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
             />
             <button
              type="submit"
              disabled={!state.sessionId || isStreaming || !input.trim()}
              className="self-end px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
             >
              <Send className="w-4 h-4" />
             </button>
           </div>
         </form>
       </div>
     );
}
