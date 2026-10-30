'use client';

import { useState, useEffect } from 'react';
import { FileWarning, Download } from 'lucide-react';
import Button from '@/components/ui/Button';
import { useSession } from '@/context/SessionContext';

// `input_too_large` SSE payload (ADR-0025). Sizes are KB — token counts never
// reach the UI. The original message + thinking flag are kept so a section
// click can resend the same request focused on that subtree.
export type TooLargeCut =
  | { path: string; kind: 'array' | 'keys'; from: number; to: number }
  | { path: string; kind: 'string'; count: number; to: number };

export type TooLargeInfo = {
  message: string;
  doc_kb: number;
  max_kb: number;
  sections: Array<{ path: string; kb: number }>;
  trimmed: { working_json: unknown; cuts: TooLargeCut[] } | null;
  userMessage: string;
  thinking: boolean;
};

// Module-level store, same pattern as RateLimitModal.
let _info: TooLargeInfo | null = null;
let _listeners: Array<() => void> = [];

function _notify() {
  for (const listener of _listeners) listener();
}

export function showTooLargeModal(info: TooLargeInfo) {
  _info = info;
  _notify();
}

export function hideTooLargeModal() {
  _info = null;
  _notify();
}

function describeCut(cut: TooLargeCut): string {
  const path = cut.path || '/';
  if (cut.kind === 'string') return `${path}: ${cut.count} values shortened to ${cut.to} chars`;
  return `${path}: ${cut.from} → ${cut.to} ${cut.kind === 'keys' ? 'keys' : 'items'}`;
}

function downloadJson(value: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function TooLargeModal() {
  const { sendMessage } = useSession();
  const [info, setInfo] = useState<TooLargeInfo | null>(null);

  useEffect(() => {
    const handler = () => setInfo(_info);
    _listeners.push(handler);
    handler();
    return () => {
      _listeners = _listeners.filter((l) => l !== handler);
    };
  }, []);

  if (!info) return null;

  const focus = (path: string) => {
    hideTooLargeModal();
    sendMessage(info.userMessage, info.thinking, path);
  };

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/25"
      onClick={() => hideTooLargeModal()}
    >
      <div
        className="mx-4 w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-100 text-purple-600">
            <FileWarning className="h-[1.125rem] w-[1.125rem]" />
          </span>
          <h3 className="text-lg font-semibold">JSON too large for the AI model</h3>
        </div>

        <p className="mb-4 text-sm text-gray-500">{info.message}</p>

        {info.sections.length > 0 && (
          <div className="mb-4">
            <p className="mb-2 text-sm font-medium text-gray-700">Edit one section</p>
            <div className="flex flex-col gap-1.5">
              {info.sections.map((s) => (
                <Button
                  key={s.path}
                  variant="secondary"
                  size="sm"
                  className="w-full !justify-between font-mono"
                  onClick={() => focus(s.path)}
                >
                  <span className="truncate">{s.path}</span>
                  <span className="font-sans text-xs text-gray-500">~{s.kb} KB</span>
                </Button>
              ))}
            </div>
          </div>
        )}

        {info.trimmed && (
          <div className="mb-4">
            <p className="mb-1 text-sm font-medium text-gray-700">Or work on a trimmed copy</p>
            <ul className="mb-2 max-h-24 list-disc overflow-y-auto pl-5 text-xs text-gray-500">
              {info.trimmed.cuts.slice(0, 8).map((c) => (
                <li key={`${c.kind}:${c.path}`}>{describeCut(c)}</li>
              ))}
            </ul>
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              onClick={() => downloadJson(info.trimmed!.working_json, 'trimmed.json')}
            >
              <Download className="h-4 w-4" />
              Download trimmed copy
            </Button>
            <p className="mt-1 text-xs text-gray-400">
              Your full JSON stays unchanged here. Upload the copy in a new session to edit it.
            </p>
          </div>
        )}

        <Button variant="primary" className="w-full" onClick={() => hideTooLargeModal()}>
          Got it
        </Button>
      </div>
    </div>
  );
}
