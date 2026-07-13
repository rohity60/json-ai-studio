'use client';

import { useState, useRef, useEffect } from 'react';
import { Briefcase, Check, ChevronDown, Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '@/context/WorkspaceContext';
import { showRateLimitModal } from '@/components/RateLimitModal';

export default function WorkspaceSwitcher() {
  const {
    workspaces,
    activeWorkspaceId,
    limits,
    loadingWorkspaces,
    loggedIn,
    selectWorkspace,
    createWorkspace,
    renameWorkspace,
    deleteWorkspace,
  } = useWorkspace();

  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [inlineError, setInlineError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCreating(false);
        setRenamingId(null);
        setInlineError(null);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const active = workspaces.find((w) => w.id === activeWorkspaceId);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      const ws = await createWorkspace(name);
      setNewName('');
      setCreating(false);
      setInlineError(null);
      await selectWorkspace(ws.id);
    } catch (err: any) {
      if (err?.detail?.error === 'duplicate') {
        setInlineError('A workspace with this name already exists.');
      } else if (err?.status === 401) {
        showRateLimitModal({ scope: 'api', kind: 'login' });
      } else {
        toast.error(String(err?.message || err));
      }
    }
  };

  const handleRename = async (id: string) => {
    const name = renameValue.trim();
    if (!name) return;
    try {
      await renameWorkspace(id, name);
      setRenamingId(null);
      setInlineError(null);
    } catch (err: any) {
      if (err?.detail?.error === 'duplicate') {
        setInlineError('A workspace with this name already exists.');
      } else {
        toast.error(String(err?.message || err));
      }
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
        title="Workspaces"
      >
        <Briefcase className="h-4 w-4 text-purple-600" />
        <span className="max-w-[140px] truncate">
          {loggedIn ? (active?.name ?? (loadingWorkspaces ? '…' : 'Workspaces')) : 'Default (local)'}
        </span>
        <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-xl border border-gray-200 bg-white p-2 shadow-xl">
          {!loggedIn ? (
            <div className="p-2">
              <div className="mb-2 flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
                <span className="font-medium">Default (local)</span>
                <Check className="h-4 w-4 text-purple-600" />
              </div>
              <p className="mb-2 px-1 text-xs text-gray-500">
                Your work lives in this browser only. Log in to create
                workspaces and keep JSONs + versions in your account.
              </p>
              <button
                className="w-full rounded-lg bg-purple-600 px-3 py-2 text-sm font-medium text-white hover:bg-purple-700"
                onClick={() => {
                  setOpen(false);
                  showRateLimitModal({ scope: 'api', kind: 'login' });
                }}
              >
                Log in to create workspaces
              </button>
            </div>
          ) : (
            <>
              {loadingWorkspaces && workspaces.length === 0 && (
                <div className="space-y-1 p-2">
                  <div className="h-8 animate-pulse rounded-lg bg-gray-100" />
                  <div className="h-8 animate-pulse rounded-lg bg-gray-100" />
                </div>
              )}
              {workspaces.map((w) => (
                <div
                  key={w.id}
                  className={`group flex items-center justify-between rounded-lg px-3 py-2 text-sm ${
                    w.id === activeWorkspaceId ? 'bg-purple-50' : 'hover:bg-gray-50'
                  }`}
                >
                  {renamingId === w.id ? (
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => { setRenameValue(e.target.value); setInlineError(null); }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRename(w.id);
                        if (e.key === 'Escape') setRenamingId(null);
                      }}
                      onBlur={() => setRenamingId(null)}
                      className="mr-2 w-full rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  ) : (
                    <button
                      className="flex flex-1 items-center gap-2 text-left"
                      onClick={async () => {
                        setOpen(false);
                        await selectWorkspace(w.id);
                      }}
                    >
                      {w.id === activeWorkspaceId ? (
                        <Check className="h-4 w-4 shrink-0 text-purple-600" />
                      ) : (
                        <span className="w-4 shrink-0" />
                      )}
                      <span className="truncate font-medium">{w.name}</span>
                      <span className="ml-auto shrink-0 text-xs text-gray-400">
                        {w.document_count}/{limits.maxJsons}
                      </span>
                    </button>
                  )}
                  <span className="ml-1 hidden shrink-0 items-center gap-0.5 group-hover:flex">
                    <button
                      title="Rename"
                      className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                      onClick={() => { setRenamingId(w.id); setRenameValue(w.name); }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    {!w.is_default && (
                      <button
                        title="Delete workspace"
                        className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                        onClick={() => {
                          if (confirm(`Delete workspace "${w.name}" and all its JSONs? This cannot be undone.`)) {
                            deleteWorkspace(w.id);
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </span>
                </div>
              ))}
              {inlineError && <p className="px-3 py-1 text-xs text-red-600">{inlineError}</p>}
              {creating ? (
                <div className="flex items-center gap-1 px-3 py-2">
                  <input
                    autoFocus
                    placeholder="Workspace name..."
                    value={newName}
                    onChange={(e) => { setNewName(e.target.value); setInlineError(null); }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCreate();
                      if (e.key === 'Escape') { setCreating(false); setNewName(''); }
                    }}
                    className="w-full rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <button
                    className="rounded bg-purple-600 px-2 py-1 text-xs font-medium text-white hover:bg-purple-700 disabled:opacity-50"
                    disabled={!newName.trim()}
                    onClick={handleCreate}
                  >
                    Add
                  </button>
                </div>
              ) : (
                <button
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-purple-600 hover:bg-purple-50"
                  onClick={() => setCreating(true)}
                >
                  <Plus className="h-4 w-4" /> New workspace…
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
