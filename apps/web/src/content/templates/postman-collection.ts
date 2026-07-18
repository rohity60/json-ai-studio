import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'postman-collection',
    slug: 'postman-collection',
    title: 'Postman Collection (v2.1)',
    description:
      'A Postman Collection v2.1 with a variable-driven base URL, bearer auth and two example requests — ready to import and run.',
    category: 'APIs',
    provider: 'Postman',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['postman', 'api', 'collection', 'http', 'testing'],
    schemaVersion: '2.1.0',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a collection-level bearer token',
      'Add a POST request that creates a user',
      'Convert the auth to API key in a header',
      'Add a test script that checks for status 200',
    ],
    relatedTemplates: ['openapi-spec'],
    relatedBlogs: ['openapi-json-explained'],
    purpose:
      'Group related HTTP requests with shared variables and auth so a team can import and run an API in seconds.',
    whenToUse:
      'Sharing an API with teammates, building a smoke-test suite, or documenting request/response examples.',
    requiredFields: [
      'info — collection name and the v2.1 schema URL',
      'item — the array of requests (or folders of requests)',
    ],
    optionalFields: [
      'variable — collection-level variables like {{baseUrl}}',
      'auth — shared authentication for all requests',
      'event — pre-request and test scripts',
    ],
    bestPractices: [
      'Drive hostnames through {{baseUrl}} so environments swap cleanly.',
      'Set auth at the collection level and inherit it per request.',
      'Add test scripts to assert status codes and response shape.',
    ],
    security: [
      'Store tokens in Postman environment variables, not in the collection JSON.',
      'Never commit a collection containing real bearer tokens to git.',
    ],
  },
  json: {
    info: {
      name: 'Example API',
      schema:
        'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
    },
    variable: [{ key: 'baseUrl', value: 'https://api.example.com/v1' }],
    auth: {
      type: 'bearer',
      bearer: [{ key: 'token', value: '{{authToken}}', type: 'string' }],
    },
    item: [
      {
        name: 'List items',
        request: {
          method: 'GET',
          url: { raw: '{{baseUrl}}/items', host: ['{{baseUrl}}'], path: ['items'] },
        },
      },
      {
        name: 'Create item',
        request: {
          method: 'POST',
          header: [{ key: 'Content-Type', value: 'application/json' }],
          body: { mode: 'raw', raw: '{\n  "name": "Widget"\n}' },
          url: { raw: '{{baseUrl}}/items', host: ['{{baseUrl}}'], path: ['items'] },
        },
      },
    ],
  },
};
