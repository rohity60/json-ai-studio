import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'llm-structured-output',
    slug: 'llm-structured-output',
    title: 'LLM Structured Output Request (Claude)',
    description:
      'A Claude Messages API request that uses output_config.format to make the response match a JSON Schema, so it is valid JSON every time. Use it to extract invoice fields from free text.',
    category: 'AI',
    provider: 'Anthropic',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['structured-outputs', 'json-schema', 'llm', 'anthropic', 'claude', 'extraction'],
    schemaVersion: '2023-06-01',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a line_items array to the output schema',
      'Make due_date optional',
      'Lower effort to low for a cheap extraction route',
      'Convert this to the OpenAI response_format shape',
    ],
    relatedTemplates: ['json-schema', 'anthropic-messages-request', 'openai-chat-request'],
    relatedBlogs: ['llm-structured-outputs-json', 'json-schema-guide', 'llm-thinking-reasoning-config'],
    purpose:
      'Get machine-parseable JSON back from an LLM by constraining its output to a schema instead of asking politely in the prompt.',
    whenToUse:
      'Extraction, classification or any pipeline step where the next stage parses the model output. It replaces "respond only in JSON" prompts and assistant prefill tricks.',
    requiredFields: [
      'model / max_tokens / messages: the normal Messages API fields',
      'output_config.format.type: "json_schema"',
      'output_config.format.schema: the JSON Schema the reply must match',
    ],
    optionalFields: [
      'output_config.effort: low / medium / high / xhigh / max',
      'system: instructions on how to fill each field',
      'tools[].strict: true: the same guarantee for tool-call arguments',
    ],
    bestPractices: [
      'Mark every object additionalProperties: false and list required fields.',
      'Describe each field (description) — the model reads them as instructions.',
      'Use nullable types (["string","null"]) for facts that may be missing, rather than letting the model invent them.',
      'Still check stop_reason: a refusal or max_tokens stop can mean there is no complete JSON.',
    ],
    security: [
      'Treat extracted values as untrusted input; validate business rules after parsing.',
      'Send the API key in the x-api-key header, never in the body.',
      'Do not put secrets in the text you extract from.',
    ],
    formatSignature: ['/model', '/output_config/format/schema'],
  },
  json: {
    model: 'claude-opus-5-5',
    max_tokens: 4096,
    output_config: {
      effort: 'low',
      format: {
        type: 'json_schema',
        schema: {
          type: 'object',
          properties: {
            vendor: { type: 'string', description: 'Company that issued the invoice' },
            invoice_number: { type: 'string' },
            total: { type: 'number', description: 'Grand total including tax' },
            currency: { type: 'string', description: 'ISO 4217 code, e.g. USD' },
            due_date: {
              type: ['string', 'null'],
              description: 'YYYY-MM-DD, or null if not stated',
            },
          },
          required: ['vendor', 'invoice_number', 'total', 'currency', 'due_date'],
          additionalProperties: false,
        },
      },
    },
    system: 'Extract invoice fields. Use null when a field is not present; never guess.',
    messages: [
      {
        role: 'user',
        content:
          'Invoice #INV-2291 from Northwind Traders. Total due: $1,240.50 USD by 15 Dec 2026.',
      },
    ],
  },
};
