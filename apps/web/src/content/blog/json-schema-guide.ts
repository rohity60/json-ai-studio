import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-schema-guide',
    title: 'JSON Schema 2020-12: A Practical Guide with Examples',
    description:
      'Learn JSON Schema by example: types, required, additionalProperties, enums and formats, $defs and $ref, nullable fields and composition. Covers why 2020-12 now underpins OpenAPI 3.1, MCP tools and LLM structured outputs.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['json-schema', 'validation', '2020-12', 'openapi', 'mcp'],
    readingTime: '8 min',
    aiSummary:
      'JSON Schema describes the shape of a JSON document. Declare "$schema": "https://json-schema.org/draft/2020-12/schema", set type, list properties and required, and add additionalProperties: false to reject unknown keys. Reuse sub-schemas through $defs and $ref. Write nullable fields as type ["string","null"]. format is an annotation unless your validator asserts it. Draft 2020-12 is the dialect behind OpenAPI 3.1+, MCP tool input/output schemas and LLM structured outputs, though LLM providers support only a subset.',
    relatedTemplates: ['json-schema', 'llm-structured-output', 'openapi-spec'],
    relatedBlogs: ['llm-structured-outputs-json', 'openapi-json-explained', 'mcp-json-guide'],
    faq: [
      {
        q: 'Which JSON Schema draft should I use?',
        a: 'Use 2020-12 for new work. It is what OpenAPI 3.1+ and the MCP spec use, and current validators such as Ajv (via ajv/dist/2020) and Python jsonschema support it. Draft-07 is still common in older tools; the main visible differences are $defs instead of definitions and prefixItems instead of array-form items.',
      },
      {
        q: 'Why does my "format": "email" not reject bad emails?',
        a: 'In 2020-12, format is an annotation by default: validators record it but do not fail on it. Turn on format assertion in your validator (for example ajv-formats with Ajv) if you rely on it.',
      },
      {
        q: 'How do I make a field nullable?',
        a: 'Use a type array: {"type": ["string", "null"]}. The OpenAPI 3.0 keyword nullable: true is not JSON Schema and was dropped in OpenAPI 3.1.',
      },
      {
        q: 'Can LLMs use any JSON Schema?',
        a: 'No. Structured-output features support a subset that varies by provider. Typically every object needs additionalProperties: false, and some keywords (certain formats, very deep recursion, large enums) are limited or unsupported. Keep LLM schemas flat and explicit.',
      },
    ],
  },
  body: `JSON Schema is a JSON document that describes other JSON documents. Validators use it to accept or reject data, editors use it for autocomplete, code generators turn it into types, and in 2026 it is also how you tell an LLM exactly what to return.

## The smallest useful schema

\`\`\`json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "email": { "type": "string", "format": "email" },
    "name":  { "type": "string", "minLength": 1 }
  },
  "required": ["email", "name"],
  "additionalProperties": false
}
\`\`\`

- **\`$schema\`** names the dialect. Always include it.
- **\`properties\`** describes fields. **\`required\`** lists those that must be present. Properties are optional by default.
- **\`additionalProperties: false\`** rejects unknown keys, which catches typos like \`emial\`.

## Constraining values

| Keyword | Applies to | Example |
|---|---|---|
| \`enum\` / \`const\` | any | \`{"enum": ["admin", "editor"]}\` |
| \`minLength\` / \`maxLength\` / \`pattern\` | strings | \`{"pattern": "^[A-Z]{2}$"}\` |
| \`minimum\` / \`maximum\` / \`multipleOf\` | numbers | \`{"minimum": 0}\` |
| \`minItems\` / \`maxItems\` / \`uniqueItems\` | arrays | \`{"maxItems": 20}\` |
| \`format\` | strings | \`email\`, \`uuid\`, \`date-time\`, \`uri\` |

## Nullable fields

\`\`\`json
"nickname": { "type": ["string", "null"] }
\`\`\`

A type array is the 2020-12 way. \`nullable: true\` was an OpenAPI 3.0 invention and is not valid JSON Schema.

## Reuse with $defs and $ref

\`\`\`json
"properties": { "address": { "$ref": "#/$defs/address" } },
"$defs": {
  "address": {
    "type": "object",
    "properties": { "city": { "type": "string" } },
    "required": ["city"]
  }
}
\`\`\`

\`$defs\` replaced the older \`definitions\` keyword. \`$ref\` takes a JSON Pointer into the same document, or a URI pointing at another schema.

## Composition

- **\`oneOf\`**: exactly one sub-schema matches. Use it for tagged unions, ideally with a \`const\` discriminator field.
- **\`anyOf\`**: at least one matches.
- **\`allOf\`**: all match. Use it to layer constraints.
- **\`if\` / \`then\` / \`else\`**: conditional rules, such as "if country is US, zip is required".

## Why 2020-12 is everywhere now

- **OpenAPI 3.1+** schemas *are* 2020-12 schemas. No more separate dialect.
- **MCP** tool \`inputSchema\` / \`outputSchema\` moved to full 2020-12 in 2026.
- **LLM structured outputs** from Claude, OpenAI and Gemini constrain generation to a schema you supply, though each supports only a subset of keywords.

One schema can now drive your API docs, your agent's tool contract and your model's output format.

## Security notes

- Never let a validator dereference remote \`$ref\` URLs from a schema you don't control.
- Bound sizes (\`maxLength\`, \`maxItems\`) on any public input to avoid oversized payloads.
- A valid document is only well-shaped. You still need to check permissions and business rules.

Open the JSON Schema template and ask the workspace to "add an array of addresses using $defs" or "make phone optional with a pattern", then review the diff.`,
};
