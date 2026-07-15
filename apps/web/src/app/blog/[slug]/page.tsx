import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import SiteHeader from '@/components/site/SiteHeader';
import Breadcrumbs from '@/components/site/Breadcrumbs';
import JsonLd from '@/components/JsonLd';
import AiSummary from '@/components/blog/AiSummary';
import PostBody from '@/components/blog/PostBody';
import Faq from '@/components/blog/Faq';
import OpenTemplateCTA from '@/components/blog/OpenTemplateCTA';
import RelatedLists from '@/components/templates/RelatedLists';
import { getAllPostSlugs, getPostBySlug } from '@/lib/blog';
import { articleLd, faqLd, breadcrumbLd } from '@/lib/ld';

type Params = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return getAllPostSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const post = getPostBySlug(slug);
  if (!post) return {};
  const { meta } = post;
  const url = `/blog/${meta.slug}`;
  return {
    title: meta.title,
    description: meta.description,
    keywords: meta.tags,
    alternates: { canonical: url },
    openGraph: { title: meta.title, description: meta.description, url, type: 'article' },
    twitter: { card: 'summary_large_image', title: meta.title, description: meta.description },
  };
}

export default async function BlogPostPage({ params }: Params) {
  const { slug } = await params;
  const post = getPostBySlug(slug);
  if (!post) notFound();
  const { meta, body } = post;

  const crumbs = [
    { name: 'Home', path: '/' },
    { name: 'Blog', path: '/blog' },
    { name: meta.title, path: `/blog/${meta.slug}` },
  ];

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <SiteHeader />
      <JsonLd data={articleLd(meta)} />
      <JsonLd data={breadcrumbLd(crumbs)} />
      {meta.faq.length > 0 && <JsonLd data={faqLd(meta.faq)} />}
      <main className="mx-auto max-w-4xl px-4 py-10">
        <Breadcrumbs crumbs={crumbs} />
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">{meta.title}</h1>
        <div className="mt-2 flex items-center gap-2 text-sm text-gray-400">
          <span>{meta.readingTime}</span>
          <span>·</span>
          <span>
            {new Date(meta.updatedAt).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </span>
        </div>

        <AiSummary text={meta.aiSummary} />

        {meta.relatedTemplates[0] && <OpenTemplateCTA slug={meta.relatedTemplates[0]} />}

        <article>
          <PostBody body={body} />
        </article>

        <Faq items={meta.faq} />

        <section className="mt-10 border-t border-gray-200 pt-6">
          <RelatedLists
            templates={meta.relatedTemplates}
            blogs={meta.relatedBlogs}
          />
        </section>
      </main>
    </div>
  );
}
