import type { Metadata } from 'next';
import SiteHeader from '@/components/site/SiteHeader';
import TemplateExplorer from '@/components/templates/TemplateExplorer';
import { buildTemplateIndex, getTemplateFacets } from '@/lib/templates';

export const metadata: Metadata = {
  title: 'JSON Configuration Templates',
  description:
    'Browse ready-to-use JSON configuration templates — AWS IAM, OpenAPI, Docker, Firebase, Elasticsearch and more. Open any template in the AI Workspace to explain, customize and validate it.',
  alternates: { canonical: '/templates' },
  openGraph: {
    title: 'JSON Configuration Templates — JSON AI Studio',
    description:
      'Ready-to-use JSON configuration templates you can open in an AI Workspace to explain, edit and validate.',
    url: '/templates',
    type: 'website',
  },
};

export default function TemplatesPage() {
  const index = buildTemplateIndex();
  const facets = getTemplateFacets();

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            Configuration Templates
          </h1>
          <p className="mt-2 max-w-2xl text-gray-600">
            Real-world JSON configurations across cloud, DevOps, auth, APIs, AI and
            databases. Open any one in the AI Workspace to explain, customize, validate
            and download it.
          </p>
        </div>
        <TemplateExplorer index={index} facets={facets} />
      </main>
    </div>
  );
}
