'use client';

import { useMemo, useState } from 'react';
import { JsonView } from 'react-json-view-lite';
import 'react-json-view-lite/dist/index.css';
import { Check, X, Code, Columns } from 'lucide-react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer';
import { toast } from 'sonner';
import { useSession } from '@/context/SessionContext';
import Button from '@/components/ui/Button';
import { pendingDiffs } from '@/lib/chatHistory';

type DiffViewerProps = {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  onResolved?: () => void;
};

const opColors: Record<string, string> = {
  add: 'text-green-600 bg-green-50',
  modify: 'text-yellow-600 bg-yellow-50',
  delete: 'text-red-600 bg-red-50',
};

export default function DiffViewer({ before, after, onResolved }: DiffViewerProps) {
  // In-flight clicks only; resolved diffs drop out of the pending list once
  // the server confirms the new status.
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'diffviewer' | 'sidebyside'>('diffviewer');

  const { acceptDiff, removeDiff, acceptAllDiffs, rejectAllDiffs, state } = useSession();

  // Pending diffs from every turn: the user may have kept chatting without
  // resolving earlier proposals, which are still previewed in working_json.
  const localDiffs = useMemo(() => pendingDiffs(state.conversationHistory), [state.conversationHistory]);

  const resolve = async (id: string, fn: (id: string) => Promise<void>) => {
    setBusy((prev) => new Set(prev).add(id));
    try { await fn(id); } finally {
      setBusy((prev) => { const n = new Set(prev); n.delete(id); return n; });
    }
  };

  const hasDiffs = localDiffs.length > 0;

  if (Object.keys(before).length === 0 && Object.keys(after).length === 0) {
    return (
      <div className='flex items-center justify-center h-32 text-sm text-muted-foreground'>
        No diffs
      </div>
    );
  }

  const oldCode = JSON.stringify(before, null, 2);
  const newCode = JSON.stringify(after, null, 2);

  return (
    <div className='space-y-4'>
      {/* View mode toggle */}
      <div className='flex items-center gap-2 border-b pb-2 flex-wrap'>
        <Button variant="pill" active={viewMode === 'diffviewer'} onClick={() => setViewMode('diffviewer')}>
          <Code className='w-4 h-4' />
          Diff Viewer
        </Button>
        <Button variant="pill" active={viewMode === 'sidebyside'} onClick={() => setViewMode('sidebyside')}>
          <Columns className='w-4 h-4' />
          Side by Side
        </Button>
        <div className='flex-1' />
        <div className='flex items-center gap-4 text-xs text-muted-foreground flex-wrap'>
          <span className='flex items-center gap-1'>
            <span className='inline-block w-3 h-3 bg-green-400 rounded-sm' /> Added
          </span>
          <span className='flex items-center gap-1'>
            <span className='inline-block w-3 h-3 bg-yellow-400 rounded-sm' /> Modified
          </span>
          <span className='flex items-center gap-1'>
            <span className='inline-block w-3 h-3 bg-red-400 rounded-sm' /> Deleted
          </span>
        </div>
      </div>

      {/* react-diff-viewer */}
      {viewMode === 'diffviewer' && (
        <div className='border rounded-lg overflow-auto max-h-[60vh]'>
          <ReactDiffViewer
            oldValue={oldCode}
            newValue={newCode}
            compareMethod={DiffMethod.WORDS}
            splitView={true}
            showDiffOnly={true}
            extraLinesSurroundingDiff={3}
            hideLineNumbers={false}
            useDarkTheme={false}
            leftTitle='BEFORE'
            rightTitle='AFTER'
          />
        </div>
      )}

      {/* Side-by-side fallback */}
      {viewMode === 'sidebyside' && (
        <div className='grid grid-cols-2 gap-4'>
          <div className='border rounded-lg p-3 bg-white'>
            <p className='text-xs font-semibold text-muted-foreground mb-2'>BEFORE</p>
            <div className='max-h-[40vh] overflow-auto border rounded'>
              <JsonView data={before} shouldExpandNode={(level) => level < 2} />
            </div>
          </div>
          <div className='border rounded-lg p-3 bg-white'>
            <p className='text-xs font-semibold text-muted-foreground mb-2'>AFTER</p>
            <div className='max-h-[40vh] overflow-auto border rounded'>
              <JsonView data={after} shouldExpandNode={(level) => level < 2} />
            </div>
          </div>
        </div>
      )}

      {/* Change list with accept/reject */}
      {hasDiffs && (
        <div className='border-t pt-4'>
          <p className='text-sm font-semibold mb-2'>Change List ({localDiffs.length})</p>
          {localDiffs.map((diff) => (
            <div
              key={diff.id}
              className={`flex items-center justify-between p-2 rounded-lg mb-1 ${opColors[diff.operation] || ''}`}
            >
              <span className='text-xs font-mono flex gap-2'>
                {diff.path}{' '}
                <span className='uppercase'>{diff.operation}</span>
              </span>
              <div className='flex gap-1'>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => resolve(diff.id, acceptDiff)}
                  disabled={busy.has(diff.id)}
                  className='hover:bg-black/10'
                  title='Accept'
                >
                  <Check className='w-4 h-4 text-green-600' />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => resolve(diff.id, removeDiff)}
                  disabled={busy.has(diff.id)}
                  className='hover:bg-black/10'
                  title='Reject'
                >
                  <X className='w-4 h-4 text-red-600' />
                </Button>
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

      {/* Accept/Reject all */}
      <div className='flex justify-end gap-2 pt-4 border-t'>
        <Button
          variant="success"
          size="md"
          onClick={async () => {
            await acceptAllDiffs();
            toast.success('All changes applied');
            onResolved?.();
          }}
          disabled={!hasDiffs}
        >
          Accept All
        </Button>
        <Button
          variant="danger"
          size="md"
          onClick={async () => {
            await rejectAllDiffs();
            toast.success('All changes rejected');
            onResolved?.();
          }}
          disabled={!hasDiffs}
        >
          Reject All
        </Button>
      </div>
    </div>
  );
}
