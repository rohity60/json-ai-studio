'use client';

import { ListChecks } from 'lucide-react';
import Button from '@/components/ui/Button';
import type { JobProposal } from '@/lib/api';
import { formatDuration } from '@/lib/progress';

/** Proposal for a whole-document review as a batch job (ADR-0026, WC-01).
 *  The numbers come from the server's batch packer — the same one that
 *  sizes the real batches — so they describe the run that Start begins. */
export default function JobProposalCard({ proposal, onStart, onDismiss, disabled }: {
  proposal: JobProposal;
  onStart?: () => void;
  onDismiss?: () => void;
  disabled?: boolean;
}) {
  const stat = (label: string, value: string) => (
    <div className="rounded border bg-white px-2 py-1.5">
      <dt className="text-[10px] uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="text-sm font-semibold text-gray-900">{value}</dd>
    </div>
  );
  return (
    <div className="mt-2 rounded-lg border border-purple-200 bg-purple-50 p-3 whitespace-normal" data-testid="job-proposal">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-purple-800">
        <ListChecks className="w-3.5 h-3.5" />
        Review in batches
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2">
        {stat('Items', proposal.record_count.toLocaleString())}
        {stat('Batches', proposal.batch_count.toLocaleString())}
        {stat('Estimated time', `~${formatDuration(proposal.eta_s * 1000)}`)}
      </dl>
      <p className="mt-2 text-[11px] text-gray-600">
        Scope: <span className="font-mono">{proposal.scope_path || '(whole document)'}</span>
      </p>
      <p className="mt-1 text-[11px] text-gray-600 break-words">
        Instruction: <span className="italic">{proposal.instruction}</span>
      </p>
      {(onStart || onDismiss) && (
        <div className="mt-3 flex gap-2">
          {onStart && (
            <Button variant="primary" onClick={onStart} disabled={disabled}>Start review</Button>
          )}
          {onDismiss && (
            <Button variant="secondary" onClick={onDismiss}>Dismiss</Button>
          )}
        </div>
      )}
    </div>
  );
}
