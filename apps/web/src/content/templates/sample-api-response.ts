import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'sample-api-response',
    slug: 'sample-api-response',
    title: 'Sample REST API JSON Response (Paginated)',
    description:
      'A realistic paginated REST API response: a data array, pagination metadata, HATEOAS-style links and an empty errors array. Use it to mock an endpoint, test a frontend, or as a Postman example response.',
    category: 'APIs',
    provider: 'Generic',
    difficulty: 'beginner',
    estimatedReadTime: '4 min',
    tags: ['api response', 'sample json api', 'rest', 'pagination', 'mock api', 'postman'],
    schemaVersion: 'REST (JSON)',
    featured: false,
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Turn this into an error response for a 404',
      'Switch pagination from page numbers to a cursor',
      'Add a "createdAt" timestamp to every order',
      'Write the JSON Schema for this response',
    ],
    relatedTemplates: ['sample-json-data', 'openapi-spec', 'postman-collection', 'json-schema'],
    relatedBlogs: ['sample-json-data-guide', 'openapi-json-explained', 'json-schema-guide'],
    purpose:
      'Show the common envelope of a list endpoint: the records themselves, how many there are, how to get the next page, and where errors go.',
    whenToUse:
      'Mocking a backend before it exists, writing frontend tests, documenting an endpoint in OpenAPI examples, or saving as a Postman example response.',
    requiredFields: [
      'data: the array of records (an empty array, not null, when there are no results)',
    ],
    optionalFields: [
      'meta.pagination: page, perPage, total, totalPages (offset style) or nextCursor (cursor style)',
      'links: self / next / prev URLs so clients do not build them by hand',
      'errors: array of { code, message, field } objects; empty on success',
      'meta.requestId: correlates the response with server logs',
    ],
    bestPractices: [
      'Return [] for no results, never null; clients can always iterate.',
      'Prefer cursor pagination for large or fast-changing tables; page numbers skip or repeat rows when data shifts.',
      'Use the same envelope on every endpoint so clients can share one parser.',
      'Use ISO 8601 UTC timestamps and string ids (64-bit numeric ids lose precision in JavaScript).',
      'Put the HTTP status in the status line; do not repeat it as a "success": true field.',
    ],
    security: [
      'Never include stack traces, SQL or internal hostnames in error messages.',
      'Return only the fields the caller is allowed to see; do not rely on the client to hide them.',
    ],
    formatSignature: ['/data', '/meta/pagination'],
  },
  json: {
    data: [
      {
        id: 'ord_8f3a2c',
        status: 'shipped',
        total: { amount: 5998, currency: 'USD' },
        customer: { id: 'cus_19b7', name: 'Asha Rao', email: 'asha.rao@example.com' },
        items: [
          { sku: 'TSHIRT-BASIC', quantity: 2, unitPrice: 1999 },
          { sku: 'MUG-12OZ', quantity: 2, unitPrice: 1000 },
        ],
        createdAt: '2026-11-20T14:05:12Z',
      },
      {
        id: 'ord_8f3a2d',
        status: 'pending',
        total: { amount: 950, currency: 'USD' },
        customer: { id: 'cus_2c11', name: 'Daniel Okafor', email: 'daniel.okafor@example.com' },
        items: [{ sku: 'MUG-12OZ', quantity: 1, unitPrice: 950 }],
        createdAt: '2026-11-21T08:41:03Z',
      },
    ],
    meta: {
      requestId: 'req_01HZX4K8T2',
      pagination: { page: 1, perPage: 2, total: 37, totalPages: 19 },
    },
    links: {
      self: 'https://api.example.com/v1/orders?page=1&perPage=2',
      next: 'https://api.example.com/v1/orders?page=2&perPage=2',
      prev: null,
    },
    errors: [],
  },
};
