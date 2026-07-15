'use client';

import { ArrowRight, Loader2 } from 'lucide-react';
import { useOpenInWorkspace } from '@/lib/openInWorkspace';
import type { TemplateMeta } from '@/content/types';

/** Primary "Open in AI Workspace" CTA (template hero + blog embeds). */
export default function OpenInWorkspaceButton({
  meta,
  json,
  label = 'Open in AI Workspace',
}: {
  meta: TemplateMeta;
  json: unknown;
  label?: string;
}) {
  const { open, pending } = useOpenInWorkspace();
  return (
    <button
      onClick={() => open(meta, json, '', 'hero')}
      disabled={pending !== null}
      className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-purple-700 disabled:opacity-50"
    >
      {pending === 'hero' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
      {label}
    </button>
  );
}
