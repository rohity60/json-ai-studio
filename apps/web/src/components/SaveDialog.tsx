'use client';

import { useState, useEffect } from 'react';
import { Save, FileJson2 } from 'lucide-react';
import Button from '@/components/ui/Button';
import { useWorkspace } from '@/context/WorkspaceContext';

// Module-level store (VersionModal pattern). Promise-based: guardDirty()
// and the header Save button await whether the save actually happened.

let _resolve: ((saved: boolean) => void) | null = null;
let _open = false;
let _listeners: Array<() => void> = [];

function _notify() {
  for (const listener of _listeners) listener();
}

export function showSaveDialog(): Promise<boolean> {
  if (_resolve) _resolve(false);
  _open = true;
  const p = new Promise<boolean>((resolve) => {
    _resolve = resolve;
  });
  _notify();
  return p;
}

function settle(saved: boolean) {
  _open = false;
  const resolve = _resolve;
  _resolve = null;
  _notify();
  resolve?.(saved);
}

const NEW_WS = '__new__';
const NEW_DOC = '__new__';

export default function SaveDialog() {
  const {
    workspaces,
    activeWorkspaceId,
    documents,
    activeDocumentId,
    limits,
    pendingSave,
    fullSave,
    saveWork,
  } = useWorkspace();

  const [open, setOpen] = useState(false);
  const [wsChoice, setWsChoice] = useState<string>(NEW_WS);
  const [newWsName, setNewWsName] = useState('');
  const [docChoice, setDocChoice] = useState<string>(NEW_DOC);
  const [tag, setTag] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  useEffect(() => {
    const handler = () => setOpen(_open);
    _listeners.push(handler);
    handler();
    return () => {
      _listeners = _listeners.filter((l) => l !== handler);
    };
  }, []);

  // Re-seed the form each time the dialog opens.
  useEffect(() => {
    if (!open) return;
    setWsChoice(activeWorkspaceId ?? (workspaces[0]?.id ?? NEW_WS));
    setNewWsName('');
    setDocChoice(activeDocumentId ?? NEW_DOC);
    setTag('');
    setError(null);
    setFieldError(null);
    setSaving(false);
  }, [open, activeWorkspaceId, activeDocumentId, workspaces]);

  if (!open) return null;

  const selectedWs = workspaces.find((w) => w.id === wsChoice);
  // Documents only exist for the ACTIVE workspace list; when saving into a
  // different workspace the doc picker offers "new JSON" only.
  const docsForChoice = wsChoice === activeWorkspaceId ? documents : [];
  const selectedDoc = docsForChoice.find((d) => d.id === docChoice);
  const appendMode = !!selectedDoc;
  // Append into the loaded document → only what's new since the baseline.
  // New JSON (or another document) → the full session, it's a copy; the
  // baseline-relative pendingSave would be empty after an earlier save and
  // wrongly disable the button. saveWork dedupes appends by content anyway.
  const source =
    appendMode && docChoice === activeDocumentId ? pendingSave : fullSave;
  const pendingCount = source.versions.length + (source.workingChanged ? 1 : 0);

  const slotsUsed = appendMode ? selectedDoc.version_count + pendingCount : pendingCount;
  const overVersionLimit = slotsUsed > limits.maxVersions;
  const wsFull =
    !appendMode && !!selectedWs && selectedWs.document_count >= limits.maxJsons;
  const needsWsName = wsChoice === NEW_WS && !newWsName.trim();
  const needsTag = !appendMode && !tag.trim();
  const disabled =
    saving || pendingCount === 0 || overVersionLimit || wsFull || needsWsName || needsTag;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setFieldError(null);
    try {
      await saveWork({
        workspaceId: wsChoice === NEW_WS ? undefined : wsChoice,
        newWorkspaceName: wsChoice === NEW_WS ? newWsName.trim() : undefined,
        documentId: appendMode ? selectedDoc!.id : undefined,
        tag: appendMode ? undefined : tag.trim(),
      });
      settle(true);
    } catch (err: any) {
      const detail = err?.detail;
      if (err?.status === 401) {
        settle(false);
        // Context funnel shows the login CTA on the next call; keep it simple here.
        setSaving(false);
        return;
      }
      if (detail?.error === 'duplicate') {
        setFieldError(
          detail.field === 'tag'
            ? 'This tag is already used in the workspace — pick another.'
            : 'A workspace with this name already exists.',
        );
      } else if (detail?.error === 'limit_exceeded') {
        setError(
          detail.limit_type === 'jsons'
            ? `Workspace is full (${detail.limit} JSONs) — delete a JSON first.`
            : `Version limit reached (${detail.limit}) — delete a version first.`,
        );
      } else {
        setError(String(err?.message || err));
      }
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/25"
      onClick={() => settle(false)}
    >
      <div
        className="mx-4 w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-100 text-purple-600">
            <Save className="h-[18px] w-[18px]" />
          </span>
          <h3 className="text-lg font-semibold">Save to workspace</h3>
        </div>

        {/* Workspace picker */}
        <label className="mb-1 block text-xs font-medium text-gray-600">Workspace</label>
        <select
          value={wsChoice}
          onChange={(e) => { setWsChoice(e.target.value); setDocChoice(NEW_DOC); setFieldError(null); }}
          className="mb-2 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name} ({w.document_count}/{limits.maxJsons})
            </option>
          ))}
          <option value={NEW_WS}>+ New workspace…</option>
        </select>
        {wsChoice === NEW_WS && (
          <input
            autoFocus
            placeholder="Workspace name..."
            value={newWsName}
            onChange={(e) => { setNewWsName(e.target.value); setFieldError(null); }}
            className="mb-2 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        )}

        {/* Document: append vs new */}
        <label className="mb-1 block text-xs font-medium text-gray-600">JSON</label>
        <select
          value={docChoice}
          onChange={(e) => { setDocChoice(e.target.value); setFieldError(null); }}
          className="mb-2 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        >
          <option value={NEW_DOC}>+ Save as new JSON…</option>
          {docsForChoice.map((d) => (
            <option key={d.id} value={d.id}>
              {d.tag} ({d.version_count}/{limits.maxVersions} versions)
            </option>
          ))}
        </select>
        {!appendMode && (
          <input
            placeholder="Tag (e.g. payment-config)..."
            value={tag}
            onChange={(e) => { setTag(e.target.value); setFieldError(null); }}
            className="mb-2 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        )}
        {fieldError && <p className="mb-2 text-xs text-red-600">{fieldError}</p>}

        {/* Version summary */}
        <div className="mb-3 rounded-lg bg-gray-50 p-3">
          <p className="mb-1 text-xs font-medium text-gray-600">Will save:</p>
          <ul className="space-y-0.5 text-xs text-gray-700">
            {source.versions.map((v, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <FileJson2 className="h-3 w-3 text-gray-400" /> {v.label || 'Unlabeled version'}
              </li>
            ))}
            {source.workingChanged && (
              <li className="flex items-center gap-1.5 font-medium text-purple-700">
                <FileJson2 className="h-3 w-3" /> +1 version (unsaved changes)
              </li>
            )}
            {pendingCount === 0 && <li className="text-gray-400">Nothing new to save</li>}
          </ul>
          <p className={`mt-1.5 text-xs ${overVersionLimit ? 'font-semibold text-red-600' : 'text-gray-500'}`}>
            {appendMode
              ? `Will use ${slotsUsed}/${limits.maxVersions} version slots of "${selectedDoc!.tag}"`
              : `Will use ${slotsUsed}/${limits.maxVersions} version slots`}
          </p>
          {overVersionLimit && (
            <p className="mt-1 text-xs text-red-600">
              Too many versions — delete some session versions or a stored version first.
            </p>
          )}
          {wsFull && (
            <p className="mt-1 text-xs text-red-600">
              Workspace is full ({limits.maxJsons} JSONs) — delete a JSON or pick another workspace.
            </p>
          )}
        </div>

        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

        <div className="flex gap-2">
          <Button variant="primary" className="flex-1" onClick={handleSave} disabled={disabled}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
          <Button variant="secondary" className="flex-1" onClick={() => settle(false)}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}
