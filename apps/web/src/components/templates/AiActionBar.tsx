'use client';

import { Sparkles, Wand2, ShieldCheck, TrendingUp, Bug, Download, Loader2 } from 'lucide-react';
import { useOpenInWorkspace } from '@/lib/openInWorkspace';
import type { TemplateMeta } from '@/content/types';

/** AI action buttons (PRD §5). Explain/Customize/Validate/Improve/Fix open the
 *  workspace seeded with a preset starter prompt; Download is a local blob. */

const ACTIONS: { key: string; label: string; prompt: string; Icon: any }[] = [
  { key: 'explain', label: 'Explain', prompt: 'Explain each field of this configuration', Icon: Sparkles },
  { key: 'customize', label: 'Customize', prompt: '', Icon: Wand2 },
  { key: 'validate', label: 'Validate', prompt: 'Validate this against best practices and flag issues', Icon: ShieldCheck },
  { key: 'improve', label: 'Improve', prompt: 'Suggest improvements to this configuration', Icon: TrendingUp },
  { key: 'fix', label: 'Fix', prompt: 'Find and fix problems in this configuration', Icon: Bug },
];

export default function AiActionBar({ meta, json }: { meta: TemplateMeta; json: unknown }) {
  const { open, pending } = useOpenInWorkspace();

  function download() {
    const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `${meta.slug}.json`,
    });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className="flex flex-wrap gap-2">
      {ACTIONS.map(({ key, label, prompt, Icon }) => (
        <button
          key={key}
          onClick={() => open(meta, json, prompt, key)}
          disabled={pending !== null}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 transition-colors hover:border-purple-300 hover:bg-purple-50 hover:text-purple-700 disabled:opacity-50"
        >
          {pending === key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />}
          {label}
        </button>
      ))}
      <button
        onClick={download}
        className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50"
      >
        <Download className="h-4 w-4" />
        Download
      </button>
    </div>
  );
}
