import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'elasticsearch-query',
    slug: 'elasticsearch-query',
    title: 'Elasticsearch bool Query',
    description:
      'An Elasticsearch Query DSL request combining full-text match, a term filter and a date range, with sorting and pagination — the everyday search shape.',
    category: 'Databases',
    provider: 'Elasticsearch',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['elasticsearch', 'search', 'query-dsl', 'database', 'bool'],
    schemaVersion: '8.x',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Sort results by date descending',
      'Add a fuzzy match on the title field',
      'Filter to the last 7 days only',
      'Add aggregations by category',
    ],
    relatedTemplates: ['mongodb-schema-validation'],
    relatedBlogs: [],
    purpose:
      'Retrieve documents that match a search term, are constrained by filters, and come back sorted and paginated.',
    whenToUse:
      'Powering a search box or filtered list view over an Elasticsearch/OpenSearch index.',
    requiredFields: [
      'query — the top-level query clause (here a bool query)',
      'bool.must / filter / should — how sub-clauses combine',
    ],
    optionalFields: [
      'sort — result ordering',
      'from / size — pagination window',
      '_source — which fields to return',
    ],
    bestPractices: [
      'Put exact-match constraints in filter (cached, no scoring), text in must.',
      'Prefer keyword fields for term filters, text fields for match.',
      'Cap size and use search_after for deep pagination.',
    ],
    security: [
      'Validate and bound user input — huge from/size values can exhaust the cluster.',
      'Never build query JSON via string concatenation of raw user input.',
    ],
  },
  json: {
    from: 0,
    size: 20,
    query: {
      bool: {
        must: [{ match: { title: 'wireless headphones' } }],
        filter: [
          { term: { category: 'electronics' } },
          { range: { created_at: { gte: 'now-30d/d', lte: 'now/d' } } },
        ],
      },
    },
    sort: [{ _score: 'desc' }, { created_at: 'desc' }],
    _source: ['id', 'title', 'category', 'price', 'created_at'],
  },
};
