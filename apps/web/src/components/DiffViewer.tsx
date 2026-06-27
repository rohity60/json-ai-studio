'use client';

import { useEffect, useState } from 'react';
import { JsonView } from 'react-json-view-lite';
import 'react-json-view-lite/dist/index.css';
import { Check, X } from 'lucide-react';
import { useSession } from '@/context/SessionContext';

type DiffEntry = {
  id: string;
  path: string;
  operation: 'add' | 'modify' | 'delete';
  old_value?: unknown;
  new_value?: unknown;
};

type DiffViewerProps = {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
};

const opColors: Record<string, string> = {
  add: 'text-green-600 bg-green-50',
  modify: 'text-yellow-600 bg-yellow-50',
  delete: 'text-red-600 bg-red-50',
};

export default function DiffViewer({ before, after }: DiffViewerProps) {
  const [localDiffs, setLocalDiffs] = useState<DiffEntry[]>([]);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [rejected, setRejected] = useState<Set<number>>(new Set());

  const { acceptDiff, removeDiff, acceptAllDiffs, rejectAllDiffs, state } = useSession();

   // Sync diffs from conversation history — backend-assigned UUIDs
  useEffect(() => {
    const entries: DiffEntry[] = [];
    for (const turn of [...state.conversationHistory].reverse()) {
      if (turn.role === 'assistant' && turn.diffs?.length) {
        for (const d of turn.diffs) {
          entries.push({
            id: String(d.id ?? ''),
            path: String(d.path ?? ''),
            operation: (d.operation as DiffEntry['operation']) || 'modify',
            old_value: d.old_value,
            new_value: d.new_value,
           });
         }
        break; // only the most recent assistant turn
       }
     }
    setLocalDiffs(entries);
    setAccepted(new Set());
    setRejected(new Set());
   }, [state.conversationHistory]);

  if (Object.keys(before).length === 0 && Object.keys(after).length === 0) {
    return <div className='flex items-center justify-center h-32 text-sm text-muted-foreground'>No diffs</div>;
   }

  const hasDiffs = localDiffs.length > 0;

  return (
     <div className='space-y-4'>
       <div className='grid grid-cols-2 gap-4'>
         <div className='border rounded-lg p-3 bg-white'>
           <p className='text-xs font-semibold text-muted-foreground mb-2'>BEFORE</p>
           <div className='max-h-[40vh] overflow-auto border rounded'><JsonView data={before} shouldExpandNode={(level) => level < 2} /></div>
         </div>
         <div className='border rounded-lg p-3 bg-white'>
           <p className='text-xs font-semibold text-muted-foreground mb-2'>AFTER</p>
           <div className='max-h-[40vh] overflow-auto border rounded'><JsonView data={after} shouldExpandNode={(level) => level < 2} /></div>
         </div>
       </div>
       {hasDiffs && (
         <div className='border-t pt-4'>
           <p className='text-sm font-semibold mb-2'>Change List ({localDiffs.length})</p>
           {localDiffs.map((diff, i) => (
             <div key={diff.id} className={`flex items-center justify-between p-2 rounded-lg mb-1 ${opColors[diff.operation]}`}>
               <span className='text-xs font-mono flex gap-2'>{diff.path} <span className='uppercase'>{diff.operation}</span></span>
               <div className='flex gap-1'>
                 <button
                   onClick={() => { acceptDiff(diff.id); setAccepted(prev => new Set([...prev, i])); }}
                   disabled={accepted.has(i)}
                   className='p-1 hover:bg-black/10 rounded'
                   title='Accept'
                  ><Check className='w-4 h-4 text-green-600' /></button>
                 <button
                   onClick={() => { removeDiff(diff.id); setRejected(prev => new Set([...prev, i])); }}
                   disabled={rejected.has(i)}
                   className='p-1 hover:bg-black/10 rounded'
                   title='Reject'
                  ><X className='w-4 h-4 text-red-600' /></button>
               </div>
             </div>
           ))}
         </div>
       )}
       {!hasDiffs && (
         <div className='border-t pt-4 text-sm text-muted-foreground'>
          No diff actions available. Send a chat message to generate diffs, or view the JSON above.
         </div>
       )}
       <div className='flex justify-end gap-2 pt-4 border-t'>
         <button
           onClick={async () => {
             await acceptAllDiffs();
             setAccepted(new Set(localDiffs.map((_, i) => i)));
           }}
           disabled={accepted.size === localDiffs.length && rejected.size === 0}
           className='px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50'
          >Accept All</button>
         <button
           onClick={async () => {
             await rejectAllDiffs();
             setRejected(new Set(localDiffs.map((_, i) => i)));
           }}
           disabled={rejected.size === localDiffs.length && accepted.size === 0}
           className='px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50'
          >Reject All</button>
       </div>
     </div>
   );
}