import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'openapi-json-explained',
    title: 'OpenAPI JSON Explained',
    description:
      'Understand the shape of an OpenAPI 3.1 document — info, servers, paths, operations and reusable components — and how it drives docs and codegen.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['openapi', 'swagger', 'api', 'json'],
    readingTime: '5 min',
    aiSummary:
      'An OpenAPI document describes a REST API: info and servers at the top, paths with operations in the middle, and reusable schemas and security schemes under components. Tools turn it into docs, mocks and SDKs.',
    relatedTemplates: ['openapi-spec', 'postman-collection'],
    relatedBlogs: [],
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

- **openapi** — the spec version.
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

## Why it matters

From one OpenAPI file you can generate interactive docs, server stubs, typed client SDKs and mock servers. That is why "contract-first" API design starts here.

Open the OpenAPI starter template and ask the workspace to "add a DELETE operation" or "add pagination" — then review the change as a diff.`,
};
