import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'openapi-spec',
    slug: 'openapi-spec',
    title: 'OpenAPI 3.1 Specification (Starter)',
    description:
      'A minimal but complete OpenAPI 3.1 document with one CRUD resource, reusable schemas and an API-key security scheme — a clean base for any REST API.',
    category: 'APIs',
    provider: 'OpenAPI',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['openapi', 'swagger', 'rest', 'api', 'schema', 'contract'],
    schemaVersion: '3.1.0',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain the structure of this spec',
      'Add a DELETE /items/{id} operation',
      'Add pagination to the list endpoint',
      'Generate an example response for GET /items',
    ],
    relatedTemplates: ['postman-collection'],
    relatedBlogs: ['openapi-json-explained'],
    purpose:
      'Define the contract for a small REST API — paths, request/response schemas, and security — in a single OpenAPI 3.1 document.',
    whenToUse:
      'Starting a new API, generating client SDKs or server stubs, or documenting an existing service contract-first.',
    requiredFields: [
      'openapi — the spec version ("3.1.0")',
      'info — title and version of the API',
      'paths — the endpoints and their operations',
    ],
    optionalFields: [
      'components.schemas — reusable data models',
      'components.securitySchemes — auth definitions',
      'servers — base URLs per environment',
    ],
    bestPractices: [
      'Define schemas once under components and $ref them everywhere.',
      'Give every operation an operationId for codegen.',
      'Document error responses (4xx/5xx), not just the happy path.',
    ],
    security: [
      'Declare securitySchemes and apply them with a global or per-op security block.',
      'Never embed real API keys or tokens in examples.',
    ],
  },
  json: {
    openapi: '3.1.0',
    info: { title: 'Items API', version: '1.0.0' },
    servers: [{ url: 'https://api.example.com/v1' }],
    security: [{ ApiKeyAuth: [] }],
    paths: {
      '/items': {
        get: {
          operationId: 'listItems',
          summary: 'List items',
          responses: {
            '200': {
              description: 'A list of items',
              content: {
                'application/json': {
                  schema: { type: 'array', items: { $ref: '#/components/schemas/Item' } },
                },
              },
            },
          },
        },
        post: {
          operationId: 'createItem',
          summary: 'Create an item',
          requestBody: {
            required: true,
            content: {
              'application/json': { schema: { $ref: '#/components/schemas/NewItem' } },
            },
          },
          responses: { '201': { description: 'Created' } },
        },
      },
    },
    components: {
      securitySchemes: {
        ApiKeyAuth: { type: 'apiKey', in: 'header', name: 'X-API-Key' },
      },
      schemas: {
        Item: {
          type: 'object',
          required: ['id', 'name'],
          properties: {
            id: { type: 'string', format: 'uuid' },
            name: { type: 'string' },
            createdAt: { type: 'string', format: 'date-time' },
          },
        },
        NewItem: {
          type: 'object',
          required: ['name'],
          properties: { name: { type: 'string' } },
        },
      },
    },
  },
};
