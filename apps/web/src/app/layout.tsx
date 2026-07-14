import type { Metadata } from 'next';
import './globals.css';
import JsonLd from '@/components/JsonLd';

const SITE_URL = 'https://jsonaistudio.com';
const REPO_URL = 'https://github.com/rohity60/json-ai-studio';

// schema.org entity graph so AI assistants and search engines can identify the
// product, its publisher and the site. Emitted site-wide from the root layout.
const siteJsonLd = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': ['SoftwareApplication', 'WebApplication'],
      '@id': `${SITE_URL}/#app`,
      name: 'JSON AI Studio',
      description:
        'AI-powered JSON workspace to format, explain, edit, validate, diff and version JSON using natural language.',
      applicationCategory: 'DeveloperApplication',
      operatingSystem: 'Web',
      url: SITE_URL,
      featureList: [
        'AI JSON formatter',
        'Natural-language JSON editing',
        'AI JSON explanation',
        'Side-by-side JSON diffs',
        'JSON validation',
        'Version history',
        'Workspaces for saved, organized JSON documents',
      ],
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      publisher: { '@id': `${SITE_URL}/#org` },
    },
    {
      '@type': 'Organization',
      '@id': `${SITE_URL}/#org`,
      name: 'JSON AI Studio',
      url: SITE_URL,
      logo: `${SITE_URL}/icon.svg`,
      sameAs: [REPO_URL],
    },
    {
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      name: 'JSON AI Studio',
      url: SITE_URL,
      publisher: { '@id': `${SITE_URL}/#org` },
    },
  ],
};

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
        <body className="antialiased">
          <JsonLd data={siteJsonLd} />
          {children}
        </body>
      </html>
    );
}
