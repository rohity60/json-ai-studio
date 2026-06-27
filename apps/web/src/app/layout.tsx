import type { Metadata } from 'next';
import './globals.css';
import { SessionProvider } from '@/context/SessionContext';
import { Toaster } from 'sonner';

export const metadata: Metadata = {
  title: 'JSON AI Studio',
  description: 'AI-powered configuration management platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <SessionProvider>
          {children}
          <Toaster position="top-right" />
        </SessionProvider>
      </body>
    </html>
  );
}
