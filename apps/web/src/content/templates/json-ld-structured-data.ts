import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'json-ld-structured-data',
    slug: 'json-ld-structured-data',
    title: 'JSON-LD Structured Data (Schema.org Article)',
    description:
      'A schema.org Article in JSON-LD with author, publisher, dates and image, plus a BreadcrumbList in the same @graph. This is the markup search engines read for rich results.',
    category: 'Web',
    provider: 'Schema.org',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['json-ld', 'schema.org', 'seo', 'structured-data', 'rich-results'],
    schemaVersion: 'schema.org',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Convert this to a Product with an Offer and price',
      'Add an FAQPage node to the @graph',
      'Add a second author',
      'Change this to an Organization with a logo and sameAs links',
    ],
    relatedTemplates: ['json-schema'],
    relatedBlogs: ['json-ld-structured-data-guide'],
    purpose:
      'Describe a page in machine-readable form (what it is, who wrote it, when) so search engines and AI crawlers can understand it and show rich results.',
    whenToUse:
      'Blog posts, product pages, recipes, events, organizations and breadcrumbs. Embed it in a <script type="application/ld+json"> tag in the page head or body.',
    requiredFields: [
      '@context: "https://schema.org"',
      '@type: the entity type, e.g. Article, Product, Organization',
    ],
    optionalFields: [
      '@graph: several linked entities in one block',
      '@id: a stable URI so entities can reference each other',
      'headline / datePublished / dateModified / author / image: the usual Article properties',
      'publisher: the Organization behind the page',
    ],
    bestPractices: [
      'Markup must match what is visible on the page; hidden or invented claims can cost you rich results.',
      'Use ISO 8601 dates with a timezone (2026-11-21T09:00:00+00:00).',
      'Give entities an @id and reference them instead of repeating them.',
      'Test with a rich results testing tool before shipping.',
    ],
    security: [
      'Escape "</" when injecting JSON-LD server-side, or a value containing </script> can break out of the tag (XSS).',
      'Never put private data in structured data; it is public and crawled.',
    ],
    formatSignature: ['/@context', '/@graph'],
  },
  json: {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Article',
        '@id': 'https://example.com/blog/json-schema-guide#article',
        headline: 'The JSON Schema 2020-12 Guide',
        description: 'How to write and validate JSON Schema documents.',
        image: ['https://example.com/images/json-schema-cover.png'],
        datePublished: '2026-11-21T09:00:00+00:00',
        dateModified: '2026-11-21T09:00:00+00:00',
        author: {
          '@type': 'Person',
          name: 'Jane Doe',
          url: 'https://example.com/authors/jane',
        },
        publisher: { '@id': 'https://example.com/#org' },
        mainEntityOfPage: 'https://example.com/blog/json-schema-guide',
      },
      {
        '@type': 'Organization',
        '@id': 'https://example.com/#org',
        name: 'Example Inc.',
        logo: 'https://example.com/logo.png',
      },
      {
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Blog', item: 'https://example.com/blog' },
          { '@type': 'ListItem', position: 2, name: 'JSON Schema Guide' },
        ],
      },
    ],
  },
};
