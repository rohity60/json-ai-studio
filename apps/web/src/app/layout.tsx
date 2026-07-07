import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://jsonaistudio.com'),
  title: {
    default: 'AI JSON Formatter Online — JSON AI Studio',
    template: '%s — JSON AI Studio',
  },
  description:
    'Free online AI JSON formatter and editor. Upload JSON, ask AI to format or modify it without breaking it, compare side-by-side diffs, and save versions.',
  keywords: [
    'json formatter',
    'ai json formatter',
    'json formatter online',
    'format json online',
    'json editor',
    'ai json tool',
    'json diff',
    'json explainer',
  ],
  openGraph: {
    title: 'AI JSON Formatter Online — JSON AI Studio',
    description:
      'Format, edit, and explain JSON with AI. Diffs, versions, multiple sessions — without ever breaking your JSON.',
    url: '/',
    siteName: 'JSON AI Studio',
    type: 'website',
  },
  twitter: {
    card: 'summary',
    title: 'AI JSON Formatter Online — JSON AI Studio',
    description: 'Format, edit, and explain JSON with AI — diffs, versions, and safe edits.',
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
