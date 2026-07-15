import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import SiteHeader from '@/components/site/SiteHeader';
import Breadcrumbs from '@/components/site/Breadcrumbs';
import JsonLd from '@/components/JsonLd';
import JsonPreview from '@/components/templates/JsonPreview';
import AiActionBar from '@/components/templates/AiActionBar';
import OpenInWorkspaceButton from '@/components/templates/OpenInWorkspaceButton';
import DifficultyBadge from '@/components/templates/DifficultyBadge';
import TemplateDocs from '@/components/templates/TemplateDocs';
import RelatedLists from '@/components/templates/RelatedLists';
import { getAllTemplateSlugs, getTemplateBySlug } from '@/lib/templates';
import { techArticleLd, breadcrumbLd } from '@/lib/ld';

type Params = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return getAllTemplateSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const tpl = getTemplateBySlug(slug);
  if (!tpl) return {};
  const { meta } = tpl;
  const url = `/templates/${meta.slug}`;
  return {
    title: `${meta.title} — JSON Template`,
    description: meta.description,
    keywords: meta.tags,
    alternates: { canonical: url },
    openGraph: { title: meta.title, description: meta.description, url, type: 'article' },
    twitter: { card: 'summary_large_image', title: meta.title, description: meta.description },
  };
}

export default async function TemplatePage({ params }: Params) {
  const { slug } = await params;
  const tpl = getTemplateBySlug(slug);
  if (!tpl) notFound();
  const { meta, json } = tpl;

  const crumbs = [
    { name: 'Home', path: '/' },
    { name: 'Templates', path: '/templates' },
    { name: meta.title, path: `/templates/${meta.slug}` },
  ];

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <SiteHeader />
      <JsonLd data={techArticleLd(meta)} />
      <JsonLd data={breadcrumbLd(crumbs)} />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <Breadcrumbs crumbs={crumbs} />

        {/* Hero */}
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-purple-600">
              {meta.provider} · {meta.category}
            </span>
            <DifficultyBadge difficulty={meta.difficulty} />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">{meta.title}</h1>
          <p className="mt-2 text-gray-600">{meta.description}</p>
          <div className="mt-3 flex flex-wrap gap-1">
            {meta.tags.map((t) => (
              <span key={t} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {t}
              </span>
            ))}
          </div>
          <div className="mt-5">
            <OpenInWorkspaceButton meta={meta} json={json} />
          </div>
        </div>

        {/* Preview */}
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Preview</h2>
          <JsonPreview json={json} />
        </section>

        {/* AI actions */}
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">AI actions</h2>
          <AiActionBar meta={meta} json={json} />
        </section>

        {/* Documentation */}
        <section className="mb-8">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Documentation</h2>
          <TemplateDocs meta={meta} />
        </section>

        {/* Related */}
        <section className="border-t border-gray-200 pt-6">
          <RelatedLists templates={meta.relatedTemplates} blogs={meta.relatedBlogs} />
        </section>
      </main>
    </div>
  );
}
