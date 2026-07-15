/** schema.org JSON-LD builders for template + blog pages (PRD §12). */

import type { BlogMeta, FaqItem, TemplateMeta } from '@/content/types';

const SITE = 'https://jsonaistudio.com';

export function techArticleLd(m: TemplateMeta) {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: m.title,
    description: m.description,
    datePublished: m.updatedAt,
    dateModified: m.updatedAt,
    author: { '@type': 'Organization', name: m.author },
    keywords: m.tags.join(', '),
    url: `${SITE}/templates/${m.slug}`,
  };
}

export function articleLd(m: BlogMeta) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: m.title,
    description: m.description,
    datePublished: m.updatedAt,
    dateModified: m.updatedAt,
    author: { '@type': 'Organization', name: m.author },
    keywords: m.tags.join(', '),
    url: `${SITE}/blog/${m.slug}`,
  };
}

export function faqLd(faq: FaqItem[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faq.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  };
}

export function breadcrumbLd(
  crumbs: { name: string; path: string }[],
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: crumbs.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: c.name,
      item: `${SITE}${c.path}`,
    })),
  };
}
