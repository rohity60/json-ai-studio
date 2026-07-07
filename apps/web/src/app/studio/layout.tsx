import type { Metadata } from 'next';
import { SessionProvider } from '@/context/SessionContext';
import { Toaster } from 'sonner';
import VersionModal from '@/components/VersionModal';
import RateLimitModal from '@/components/RateLimitModal';

export const metadata: Metadata = {
  title: 'Studio',
  description:
    'Edit, format, and explain your JSON with AI. Chat to modify JSON safely, compare diffs, and manage versions.',
};

export default function StudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      {children}
      <Toaster position="top-right" />
      <VersionModal />
      <RateLimitModal />
    </SessionProvider>
  );
}
