import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://jsonaistudio.com'),
  title: {
    default: 'AI JSON Formatter & Editor — JSON AI Studio',
    template: '%s — JSON AI Studio',
   },
  description:
      'Format, explain, edit, validate and transform JSON using AI. Diffs, versions, multiple sessions — without ever breaking your JSON.',
  keywords: [
      'json formatter',
      'ai json formatter',
      'json formatter online',
      'format json online',
      'json editor',
      'ai json tool',
      'json diff',
      'json explainer',
      'json validator',
      'json transform',
    ],
  openGraph: {
    title: 'AI JSON Formatter & Editor — JSON AI Studio',
    description:
        'The complete AI-powered workspace for working with JSON. Format, explain, edit, validate and diff JSON in plain English.',
    url: '/',
    siteName: 'JSON AI Studio',
    type: 'website',
   },
  twitter: {
    card: 'summary_large_image',
    title: 'AI JSON Formatter & Editor — JSON AI Studio',
    description: 'Format, explain, edit, and validate JSON with AI — diffs, versions, and safe edits.',
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
