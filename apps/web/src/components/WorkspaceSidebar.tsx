'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileJson2,
  PanelRightClose,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { useSession } from '@/context/SessionContext';
import { useWorkspace } from '@/context/WorkspaceContext';
import { showVersionModal } from './VersionModal';
import { showRateLimitModal } from '@/components/RateLimitModal';
import Button from '@/components/ui/Button';
import * as api from '@/lib/api';
import type { WorkspaceJsonVersion } from '@/lib/api';

/** Unified workspace sidebar: JSON documents as parents, versions as child
 *  rows (one tree — they're related data, not two tabs). Header shows the
 *  active workspace's details; footer keeps the session actions. */

// Pseudo-parent id for the not-yet-saved session ("Current JSON").
const LOCAL = '__local__';

export default function WorkspaceSidebar({ onClose }: { onClose?: () => void }) {
  const { state, createVersion, exportJson, refreshSession, clearCache } =
    useSession();
  const {
    workspaces,
    activeWorkspaceId,
    documents,
    activeDocumentId,
    limits,
    loadingDocuments,
    loggedIn,
    loadDocument,
    deleteDocument,
    deleteVersion,
    refreshWorkspaces,
  } = useWorkspace();

  const [expanded, setExpanded] = useState<Set<string>>(new Set([LOCAL]));
  // Lazily fetched versions of NON-active documents (active doc children
  // come straight from session state, which is that document loaded).
  const [childCache, setChildCache] = useState<Record<string, WorkspaceJsonVersion[]>>({});
  const [loadingChildren, setLoadingChildren] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  // The loaded document always shows open; its cached copy is stale by definition.
  useEffect(() => {
    if (!activeDocumentId) return;
    setExpanded((prev) => new Set(prev).add(activeDocumentId));
    setChildCache((prev) => {
      const { [activeDocumentId]: _stale, ...rest } = prev;
      return rest;
    });
  }, [activeDocumentId]);

  const toggle = useCallback(
    async (docId: string) => {
      const isOpen = expanded.has(docId);
      setExpanded((prev) => {
        const next = new Set(prev);
        if (isOpen) next.delete(docId);
        else next.add(docId);
        return next;
      });
      // Fetch children on first expand of a non-active document.
      if (!isOpen && docId !== LOCAL && docId !== activeDocumentId && !childCache[docId]) {
        if (!activeWorkspaceId) return;
        setLoadingChildren((prev) => new Set(prev).add(docId));
        try {
          const doc = await api.getWorkspaceJson(activeWorkspaceId, docId);
          setChildCache((prev) => ({ ...prev, [docId]: doc.versions }));
        } catch {
          // Row simply shows nothing; a retry happens on next expand.
          setExpanded((prev) => {
            const next = new Set(prev);
            next.delete(docId);
            return next;
          });
        } finally {
          setLoadingChildren((prev) => {
            const next = new Set(prev);
            next.delete(docId);
            return next;
          });
        }
      }
    },
    [expanded, childCache, activeDocumentId, activeWorkspaceId],
  );

  const openDocVersion = useCallback(
    async (docId: string, versionId: string) => {
      // Load the document straight to this version — the target is baked into
      // loadDocument's single restore call, so no stale-session selectVersion.
      await loadDocument(docId, versionId);
    },
    [loadDocument],
  );

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([refreshSession(), loggedIn ? refreshWorkspaces() : Promise.resolve()]);
      setChildCache({});
    } finally {
      setRefreshing(false);
    }
  };

  const wsName = loggedIn
    ? (workspaces.find((w) => w.id === activeWorkspaceId)?.name ?? '…')
    : 'Default (local)';
  const hasLocalWork =
    Object.keys(state.workingJson ?? {}).length > 0 || state.versions.length > 0;
  const showLocalParent = !loggedIn ? hasLocalWork : hasLocalWork && activeDocumentId === null;

  const sessionVersionRows = (
    <div className="ml-5 space-y-0.5 border-l pl-2">
      {state.versions.length === 0 && (
        <p className="py-1.5 text-xs text-gray-400">No versions yet</p>
      )}
      {state.versions.map((v) => (
        <div
          key={v.id}
          onClick={() => showVersionModal(v)}
          className={`cursor-pointer rounded-md border px-2 py-1.5 transition-colors ${
            state.activeVersionId === v.id
              ? 'border-purple-300 bg-purple-50'
              : 'border-transparent hover:bg-gray-100'
          }`}
        >
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                state.activeVersionId === v.id ? 'bg-purple-600' : 'bg-gray-300'
              }`}
            />
            <span className="truncate text-xs font-medium">{v.label || 'Unnamed'}</span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex h-full flex-col">
      {/* Workspace details header (replaces the JSONs | Versions tabs) */}
      <div className="flex items-center gap-2 border-b bg-white p-3">
        <FileJson2 className="h-5 w-5 shrink-0 text-purple-600" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{wsName}</h3>
          <p className="text-xs text-gray-400">
            {loggedIn
              ? `${documents.length}/${limits.maxJsons} JSONs`
              : 'Log in to save workspaces'}
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={handleRefresh} title="Refresh" disabled={refreshing}>
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
        {onClose && (
          <Button variant="ghost" size="icon" onClick={onClose} title="Collapse">
            <PanelRightClose className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Tree: documents as parents, versions as children */}
      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {loggedIn && loadingDocuments && documents.length === 0 && (
          <div className="space-y-2 p-2">
            <div className="h-10 animate-pulse rounded-lg bg-gray-100" />
            <div className="h-10 animate-pulse rounded-lg bg-gray-100" />
          </div>
        )}

        {showLocalParent && (
          <div>
            <div className="group flex items-center rounded-lg px-1 py-1.5 hover:bg-gray-100">
              <button className="p-0.5 text-gray-400" onClick={() => toggle(LOCAL)}>
                {expanded.has(LOCAL) ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
              </button>
              <span className="flex min-w-0 flex-1 items-center gap-1.5 text-sm font-medium">
                <FileJson2 className="h-3.5 w-3.5 shrink-0 text-purple-500" />
                <span className="truncate">Current JSON</span>
                <span className="text-xs font-normal text-gray-400">(unsaved)</span>
              </span>
            </div>
            {expanded.has(LOCAL) && sessionVersionRows}
          </div>
        )}

        {loggedIn &&
          documents.map((d) => {
            const isActive = d.id === activeDocumentId;
            const isOpen = expanded.has(d.id);
            const children = isActive ? null : childCache[d.id];
            return (
              <div key={d.id}>
                <div
                  className={`group flex items-center rounded-lg px-1 py-1.5 ${
                    isActive ? 'bg-purple-50' : 'hover:bg-gray-100'
                  }`}
                >
                  <button className="p-0.5 text-gray-400" onClick={() => toggle(d.id)}>
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    className="flex min-w-0 flex-1 flex-col items-start text-left"
                    onClick={() => !isActive && loadDocument(d.id)}
                    title={isActive ? 'Currently loaded' : `Load latest version (v${d.latest_version_number})`}
                  >
                    <span className="flex w-full items-center gap-1.5 text-sm font-medium">
                      <FileJson2
                        className={`h-3.5 w-3.5 shrink-0 ${isActive ? 'text-purple-600' : 'text-purple-400'}`}
                      />
                      <span className="truncate">{d.tag}</span>
                    </span>
                    <span className="text-xs text-gray-400">
                      {d.version_count}/{limits.maxVersions} versions
                    </span>
                  </button>
                  <button
                    title="Delete JSON"
                    className="hidden rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 group-hover:block"
                    onClick={() => {
                      if (confirm(`Delete "${d.tag}" and all its versions? This cannot be undone.`)) {
                        deleteDocument(d.id);
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {isOpen && isActive && sessionVersionRows}
                {isOpen && !isActive && (
                  <div className="ml-5 space-y-0.5 border-l pl-2">
                    {loadingChildren.has(d.id) && (
                      <p className="py-1.5 text-xs text-gray-400">Loading…</p>
                    )}
                    {children?.map((v) => (
                      <div
                        key={v.id}
                        className="group flex cursor-pointer items-center gap-2 rounded-md border border-transparent px-2 py-1.5 hover:bg-gray-100"
                        onClick={() => openDocVersion(d.id, v.id)}
                        title="Load this version"
                      >
                        <span className="h-2 w-2 shrink-0 rounded-full bg-gray-300" />
                        <span className="min-w-0 flex-1 truncate text-xs font-medium">
                          {v.label || `v${v.version_number}`}
                        </span>
                        <button
                          title="Delete version"
                          className="hidden rounded p-0.5 text-gray-400 hover:bg-red-50 hover:text-red-600 group-hover:block"
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (confirm(`Delete version "${v.label || `v${v.version_number}`}"?`)) {
                              await deleteVersion(d.id, v.id);
                              setChildCache((prev) => {
                                const { [d.id]: _stale, ...rest } = prev;
                                return rest;
                              });
                              setExpanded((prev) => {
                                const next = new Set(prev);
                                next.delete(d.id);
                                return next;
                              });
                            }
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

        {loggedIn && !loadingDocuments && documents.length === 0 && !showLocalParent && (
          <p className="p-4 text-center text-sm text-gray-400">
            No JSONs saved yet. Use Save to add the current JSON here.
          </p>
        )}
        {!loggedIn && !hasLocalWork && (
          <p className="p-4 text-center text-sm text-gray-400">
            Upload a JSON to start; versions will show up here.
          </p>
        )}
        {!loggedIn && (
          <div className="p-3 text-center">
            <button
              className="rounded-lg bg-purple-600 px-3 py-2 text-xs font-medium text-white hover:bg-purple-700"
              onClick={() => showRateLimitModal({ scope: 'api', kind: 'login' })}
            >
              Log in to save
            </button>
          </div>
        )}
      </div>

      {/* Session actions (unchanged from the old Versions tab) */}
      <div className="space-y-2 border-t p-3">
        {creating ? (
          <div className="space-y-2">
            <input
              placeholder="Version label..."
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
            />
            <div className="flex gap-1">
              <Button
                variant="primary"
                className="flex-1"
                onClick={() => {
                  if (label.trim()) createVersion(label);
                  setLabel('');
                  setCreating(false);
                }}
              >
                Save
              </Button>
              <Button variant="secondary" onClick={() => { setLabel(''); setCreating(false); }}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="primary" className="w-full" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" />
            <span>New Version</span>
          </Button>
        )}
        <Button variant="secondary" className="w-full" onClick={() => exportJson()}>
          <Download className="h-4 w-4" />
          <span>Export JSON</span>
        </Button>
        <Button
          variant="secondary"
          className="w-full"
          onClick={() => clearCache()}
          title="Remove versions cached in this browser (IndexedDB)"
        >
          <Trash2 className="h-4 w-4" />
          <span>Clear cached data</span>
        </Button>
      </div>
    </div>
  );
}
