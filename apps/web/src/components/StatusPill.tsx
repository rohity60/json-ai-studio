'use client';

import { Check, Cloud, CloudOff, Loader2 } from 'lucide-react';
import { useWorkspace } from '@/context/WorkspaceContext';
import { showRateLimitModal } from '@/components/RateLimitModal';

/** Header save-status pill (Tier 1 auto-save UX). Persistence is a state you
 *  can SEE, not an event you trigger:
 *   - saved   → steady green "All changes saved"
 *   - saving  → spinner "Saving…"
 *   - unsaved → amber, click to save into the active document now
 *   - local   → signed-out; a standing invite to log in (not a pop-up)
 *  Hidden entirely until there is JSON to talk about. */
export default function StatusPill({ hasJson }: { hasJson: boolean }) {
  const { status, saveActive } = useWorkspace();

  if (!hasJson) return null;

  if (status === 'local') {
    return (
      <button
        type="button"
        onClick={() => showRateLimitModal({ scope: 'api', kind: 'login' })}
        title="Your work is kept in this browser. Log in to save it to a workspace."
        className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100"
      >
        <CloudOff className="h-3.5 w-3.5" />
        Working locally · <span className="text-purple-600">Log in to save</span>
      </button>
    );
  }

  if (status === 'saving') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Saving…
      </span>
    );
  }

  if (status === 'unsaved') {
    return (
      <button
        type="button"
        onClick={() => saveActive()}
        title="Save your changes into the current JSON"
        className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100"
      >
        <Cloud className="h-3.5 w-3.5" />
        Unsaved changes · Save
      </button>
    );
  }

  return (
    <span
      title="Every change is saved to this workspace"
      className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700"
    >
      <Check className="h-3.5 w-3.5" />
      All changes saved
    </span>
  );
}
