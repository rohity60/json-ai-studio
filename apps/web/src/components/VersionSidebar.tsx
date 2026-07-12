'use client';

import { useState, useCallback } from 'react';
import { Plus, History, Download, RefreshCw, Trash2, PanelRightClose } from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { showVersionModal } from './VersionModal';
import Button from '@/components/ui/Button';

export default function VersionSidebar({ onClose }: { onClose?: () => void }) {
  const { state, createVersion, exportJson, refreshSession, clearCache } = useSession();
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshSession();
      } finally {
      setRefreshing(false);
      }
    };

  const handleVersionSelect = useCallback((version: any) => {
      showVersionModal(version);
    }, []);

  if (!state.sessionId && state.versions.length === 0) {
    return (
        <div className='flex flex-col h-full'>
          <div className='border-b p-3 flex items-center gap-2'>
            <History className='w-5 h-5 text-purple-600' />
            <h3 className='font-semibold text-sm'>Versions</h3>
            {onClose && (
              <Button variant="ghost" size="icon" onClick={onClose} className='ml-auto' title='Collapse'>
                <PanelRightClose className='w-4 h-4' />
              </Button>
            )}
          </div>
          <div className='flex-1 flex items-center justify-center text-sm text-muted-foreground'>
            No versions yet
          </div>
        </div>
      );
    }

  return (
      <div className='flex flex-col h-full'>
        <div className='border-b p-3 flex items-center gap-2'>
          <History className='w-5 h-5 text-purple-600' />
          <h3 className='font-semibold text-sm'>Versions</h3>
          <Button variant="ghost" size="icon" onClick={handleRefresh} className='ml-auto' title='Refresh versions' disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
          {onClose && (
            <Button variant="ghost" size="icon" onClick={onClose} title='Collapse'>
              <PanelRightClose className='w-4 h-4' />
            </Button>
          )}
        </div>
        <div className='flex-1 overflow-y-auto p-2 space-y-1'>
          {state.versions.length === 0 && (
            <p className='text-xs text-muted-foreground text-center py-4'>No versions saved yet</p>
          )}
          {state.versions.map((v) => (
            <div key={v.id} onClick={() => handleVersionSelect(v)} className={`p-2 rounded-lg cursor-pointer transition-colors ${state.activeVersionId === v.id ? 'bg-purple-50 border-purple-300' : 'hover:bg-gray-50'} border`}>
              <div className='flex items-center gap-2'>
                <span className={`w-2 h-2 rounded-full ${state.activeVersionId === v.id ? 'bg-purple-600' : 'bg-gray-300'}`} />
                <span className='text-sm font-medium'>{v.label || 'Unnamed'}</span>
              </div>
              <p className='text-xs text-muted-foreground mt-1'>{(v.json_data as Record<string, any>) ? `${Object.keys(v.json_data).length} keys` : 'Empty'}</p>
            </div>
          ))}
        </div>
        <div className='border-t p-3 space-y-2'>
          {creating ? (
            <div className='space-y-2'>
              <input placeholder='Version label...' value={label} onChange={(e) => setLabel(e.target.value)} className='w-full px-3 py-2 text-sm rounded-lg border' />
              <div className='flex gap-1'>
                <Button variant="primary" className='flex-1' onClick={() => { if (label.trim()) createVersion(label); setLabel(''); setCreating(false); }}>Save</Button>
                <Button variant="secondary" onClick={() => { setLabel(''); setCreating(false); }}>Cancel</Button>
              </div>
            </div>
          ) : (
            <Button variant="primary" className='w-full' onClick={() => setCreating(true)}>
              <Plus className='w-4 h-4' />
              <span>New Version</span>
            </Button>
          )}
          <Button variant="secondary" className='w-full' onClick={() => exportJson()}>
            <Download className='w-4 h-4' />
            <span>Export JSON</span>
          </Button>
          <Button variant="secondary" className='w-full' onClick={() => clearCache()} title='Remove versions cached in this browser (IndexedDB)'>
            <Trash2 className='w-4 h-4' />
            <span>Clear cached data</span>
          </Button>
        </div>
      </div>
    );
}
