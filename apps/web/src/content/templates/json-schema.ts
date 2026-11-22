import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'json-schema',
    slug: 'json-schema',
    title: 'JSON Schema (Draft 2020-12)',
    description:
      'A JSON Schema 2020-12 document for a user record: types, required fields, formats, enums, $defs with $ref, and additionalProperties: false. The same dialect is used by OpenAPI 3.1, MCP tool schemas and LLM structured outputs.',
    category: 'Data',
    provider: 'JSON Schema',
    difficulty: 'intermediate',
    estimatedReadTime: '7 min',
    tags: ['json-schema', 'validation', '2020-12', 'structured-outputs', 'openapi'],
    schemaVersion: '2020-12',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Make phone an optional field with a pattern',
      'Add an array of addresses using $defs',
      'Allow role to be "owner" as well',
      'Convert nullable fields to type ["string", "null"]',
    ],
    relatedTemplates: ['llm-structured-output', 'openapi-spec', 'mongodb-schema-validation'],
    relatedBlogs: ['json-schema-guide', 'llm-structured-outputs-json'],
    purpose:
      'Describe the shape a JSON document must have, so validators, code generators, editors and LLMs can check or produce it.',
    whenToUse:
      'Validating API payloads or config files, generating types, adding editor autocomplete with $schema, or constraining an LLM to return valid JSON.',
    requiredFields: [
      '$schema: the dialect URI, "https://json-schema.org/draft/2020-12/schema"',
      'type: the root type, usually "object"',
    ],
    optionalFields: [
      '$id: a unique URI for this schema',
      'properties / required: the fields and which must be present',
      'additionalProperties: false rejects unknown keys',
      '$defs + $ref: reusable sub-schemas ($defs replaced "definitions" in 2019-09)',
      'enum / const / format / pattern / minimum / maxLength: value constraints',
      'oneOf / anyOf / allOf / if-then-else: composition',
    ],
    bestPractices: [
      'Always declare $schema so tools pick the right dialect.',
      'Set additionalProperties: false on objects you control; it catches typos.',
      'Use $defs and $ref instead of copy-pasting sub-schemas.',
      'Remember "format" is an annotation by default; turn on format assertion in your validator if you rely on it.',
    ],
    security: [
      'Do not let validators fetch remote $ref URLs from untrusted schemas.',
      'Bound string lengths and array sizes (maxLength, maxItems) on public inputs.',
      'Validation checks shape, not authorization; still check permissions server-side.',
    ],
    formatSignature: ['/$schema', '/properties'],
  },
  json: {
    $schema: 'https://json-schema.org/draft/2020-12/schema',
    $id: 'https://example.com/schemas/user.json',
    title: 'User',
    type: 'object',
    properties: {
      id: { type: 'string', format: 'uuid' },
      email: { type: 'string', format: 'email', maxLength: 254 },
      name: { type: 'string', minLength: 1, maxLength: 100 },
      role: { enum: ['admin', 'editor', 'viewer'] },
      age: { type: 'integer', minimum: 0, maximum: 150 },
      nickname: { type: ['string', 'null'] },
      address: { $ref: '#/$defs/address' },
      tags: {
        type: 'array',
        items: { type: 'string' },
        uniqueItems: true,
        maxItems: 20,
      },
    },
    required: ['id', 'email', 'name', 'role'],
    additionalProperties: false,
    $defs: {
      address: {
        type: 'object',
        properties: {
          street: { type: 'string' },
          city: { type: 'string' },
          country: { type: 'string', pattern: '^[A-Z]{2}$' },
        },
        required: ['city', 'country'],
        additionalProperties: false,
      },
    },
  },
};
