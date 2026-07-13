import type { Metadata } from 'next';
import { SessionProvider } from '@/context/SessionContext';
import { WorkspaceProvider } from '@/context/WorkspaceContext';
import { Toaster } from 'sonner';
import VersionModal from '@/components/VersionModal';
import RateLimitModal from '@/components/RateLimitModal';
import SaveDialog from '@/components/SaveDialog';

export const metadata: Metadata = {
  title: 'Studio',
  description:
    'Edit, format, and explain your JSON with AI. Chat to modify JSON safely, compare diffs, and manage versions.',
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      {/* WorkspaceProvider nests INSIDE SessionProvider — it drives the
          session via useSession() when loading/saving documents (ADR-0018) */}
      <WorkspaceProvider>
        {children}
        <Toaster position="top-right" />
        <VersionModal />
        <RateLimitModal />
        <SaveDialog />
      </WorkspaceProvider>
    </SessionProvider>
  );
}
