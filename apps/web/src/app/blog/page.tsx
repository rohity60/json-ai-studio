import type { Metadata } from 'next';
import SiteHeader from '@/components/site/SiteHeader';
import BlogCard from '@/components/blog/BlogCard';
import { getAllPosts } from '@/lib/blog';

export const metadata: Metadata = {
  title: 'Blog — JSON Configuration Guides',
  description:
    'Guides and explainers for real-world JSON configuration: IAM policies, OpenAPI, Docker, Firebase, Elasticsearch and more — with examples you can open in an AI Workspace.',
  alternates: { canonical: '/blog' },
  openGraph: {
    title: 'Blog — JSON AI Studio',
    description: 'Guides and explainers for real-world JSON configuration.',
    url: '/blog',
    type: 'website',
  },
};

export default function BlogIndexPage() {
  const posts = getAllPosts();
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">Blog</h1>
          <p className="mt-2 max-w-2xl text-gray-600">
            Practical guides to understanding, writing and fixing real-world JSON
            configuration files.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {posts.map((p) => (
            <BlogCard key={p.meta.slug} m={p.meta} />
          ))}
        </div>
      </main>
    </div>
  );
}
