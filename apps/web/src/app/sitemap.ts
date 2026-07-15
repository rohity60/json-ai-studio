import type { MetadataRoute } from 'next';
import { getAllTemplateSlugs } from '@/lib/templates';
import { getAllPostSlugs } from '@/lib/blog';

const SITE = 'https://jsonaistudio.com';

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: SITE, lastModified: now, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE}/studio`, lastModified: now, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${SITE}/templates`, lastModified: now, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${SITE}/blog`, lastModified: now, changeFrequency: 'weekly', priority: 0.7 },
  ];

  const templateRoutes: MetadataRoute.Sitemap = getAllTemplateSlugs().map((slug) => ({
    url: `${SITE}/templates/${slug}`,
    lastModified: now,
    changeFrequency: 'monthly',
    priority: 0.7,
  }));

  const blogRoutes: MetadataRoute.Sitemap = getAllPostSlugs().map((slug) => ({
    url: `${SITE}/blog/${slug}`,
    lastModified: now,
    changeFrequency: 'monthly',
    priority: 0.6,
  }));

  return [...staticRoutes, ...templateRoutes, ...blogRoutes];
}
