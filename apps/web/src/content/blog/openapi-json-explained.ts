import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'openapi-json-explained',
    title: 'OpenAPI JSON Explained',
    description:
      'Understand the shape of an OpenAPI 3.1 document — info, servers, paths, operations and reusable components — and how it drives docs and codegen.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['openapi', 'swagger', 'api', 'json'],
    readingTime: '5 min',
    aiSummary:
      'An OpenAPI document describes a REST API: info and servers at the top, paths with operations in the middle, and reusable schemas and security schemes under components. Tools turn it into docs, mocks and SDKs.',
    relatedTemplates: ['openapi-spec', 'postman-collection'],
    relatedBlogs: ['json-schema-guide', 'llm-structured-outputs-json'],
    faq: [
      {
        q: 'What is the difference between OpenAPI and Swagger?',
        a: 'Swagger was the original name; OpenAPI 3.x is the current standard. "Swagger" now usually refers to the tooling (Swagger UI, Swagger Editor).',
      },
      {
        q: 'Why use $ref?',
        a: 'To define a schema once under components and reuse it across many operations, keeping the document DRY and consistent.',
      },
    ],
  },
  body: `An OpenAPI document is a single JSON (or YAML) file that fully describes a REST API. Once you know its four regions, it reads easily.

## 1. Metadata

\`\`\`json
{ "openapi": "3.1.0", "info": { "title": "Items API", "version": "1.0.0" } }
\`\`\`

- **openapi** — the spec version: \`3.0.x\`, \`3.1.x\` or \`3.2.0\`. It is not your API's version; that goes in \`info.version\`.
- **info** — human metadata: title, version, description.

## 2. Servers

\`servers\` lists base URLs, usually one per environment. Clients prepend these to each path.

## 3. Paths and operations

\`paths\` is the heart of the document. Each key is a URL template; each HTTP method under it is an **operation**:

\`\`\`json
"/items": {
  "get": { "operationId": "listItems", "responses": { "200": { "description": "OK" } } }
}
\`\`\`

Give every operation an \`operationId\` — code generators use it to name functions.

## 4. Components

\`components\` holds reusable pieces: \`schemas\` (data models), \`securitySchemes\` (auth), parameters and responses. Reference them with \`$ref\`:

\`\`\`json
"schema": { "$ref": "#/components/schemas/Item" }
\`\`\`

Define a model once, reuse it everywhere.

## 3.0 vs 3.1 vs 3.2

| Version | What changed |
|---|---|
| 3.0 | Schemas are a JSON Schema *subset*; \`nullable: true\` marks nullable fields |
| 3.1 | Schemas are full **JSON Schema 2020-12**: write \`"type": ["string", "null"]\` instead of \`nullable\`; top-level \`webhooks\` added |
| 3.2 | Additive on 3.1: hierarchical \`tags\`, streaming media types (SSE, JSON Lines), a \`query\` HTTP method, \`additionalOperations\` |

Starting fresh? Use 3.1 or 3.2. Check that your codegen and docs tools support the version before you upgrade an existing spec.

## Why it matters

From one OpenAPI file you can generate interactive docs, server stubs, typed client SDKs and mock servers. That is why "contract-first" API design starts here.

Open the OpenAPI starter template and ask the workspace to "add a DELETE operation" or "add pagination" — then review the change as a diff.`,
};
