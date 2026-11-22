import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'llm-structured-outputs-json',
    title: 'Getting Valid JSON from LLMs: Structured Outputs for Claude, OpenAI and Gemini',
    description:
      'Stop parsing "please respond in JSON" replies. How schema-constrained structured outputs work for Claude (output_config.format), OpenAI (response_format json_schema) and Gemini (responseJsonSchema), with schema rules and failure cases.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['structured-outputs', 'json-schema', 'llm', 'anthropic', 'openai', 'gemini'],
    readingTime: '8 min',
    aiSummary:
      'Structured outputs constrain an LLM to emit JSON matching a schema you provide, replacing prompt-only "reply in JSON" instructions. Claude: output_config.format {type:"json_schema", schema}. OpenAI: response_format {type:"json_schema", json_schema:{name, strict:true, schema}}. Gemini: responseMimeType "application/json" plus responseJsonSchema. For tool calls, use strict: true on the tool. Schemas should set additionalProperties: false, list every field in required and use nullable types for optional facts. Always check stop reasons: refusals and max-token cut-offs may not return complete JSON.',
    relatedTemplates: ['llm-structured-output', 'json-schema', 'anthropic-messages-request', 'openai-chat-request'],
    relatedBlogs: ['json-schema-guide', 'llm-thinking-reasoning-config'],
    faq: [
      {
        q: 'Is structured output the same as JSON mode?',
        a: 'No. JSON mode only guarantees syntactically valid JSON. Structured outputs guarantee that the JSON matches your schema: the right keys, types and required fields. Prefer structured outputs whenever the provider supports them.',
      },
      {
        q: 'Structured output or tool calling?',
        a: 'Use structured output when the final answer itself should be JSON (extraction, classification). Use a tool with strict: true when the model should decide whether and how to call a function. Many agents use both.',
      },
      {
        q: 'Can I still use assistant prefill ("{") to force JSON on Claude?',
        a: 'No. Current Claude models reject assistant prefill with a 400. Use output_config.format instead; it is more reliable anyway.',
      },
      {
        q: 'Why did I get invalid or partial JSON despite a schema?',
        a: 'The usual causes are a max_tokens cut-off (raise it), a refusal (check stop_reason) or a schema feature the provider does not support. Always check the stop reason before parsing.',
      },
    ],
  },
  body: `Asking a model to "respond only in JSON" works most of the time. That still leaves enough malformed replies to break a pipeline. **Structured outputs** fix this at the decoding level: you hand the API a JSON Schema, and the reply is constrained to match it.

## Claude: output_config.format

\`\`\`json
{
  "model": "claude-opus-5-5",
  "max_tokens": 4096,
  "output_config": {
    "effort": "low",
    "format": {
      "type": "json_schema",
      "schema": {
        "type": "object",
        "properties": {
          "vendor": { "type": "string" },
          "total": { "type": "number" },
          "due_date": { "type": ["string", "null"] }
        },
        "required": ["vendor", "total", "due_date"],
        "additionalProperties": false
      }
    }
  },
  "messages": [{ "role": "user", "content": "Invoice from Northwind, $1,240.50, due 15 Dec 2026" }]
}
\`\`\`

- The text block of the response is JSON that matches the schema.
- The older top-level \`output_format\` parameter is deprecated. Use \`output_config.format\`.
- Prefill tricks (starting the assistant turn with \`{\`) return a 400 on current models. Use this instead.
- For tool arguments, set \`"strict": true\` on the tool definition (with \`additionalProperties: false\`).
- Extraction is usually a good fit for \`effort: "low"\`.

## OpenAI: response_format

\`\`\`json
{
  "model": "gpt-5.6",
  "messages": [{ "role": "user", "content": "..." }],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "invoice",
      "strict": true,
      "schema": { "type": "object", "properties": { "vendor": { "type": "string" } }, "required": ["vendor"], "additionalProperties": false }
    }
  }
}
\`\`\`

On the Responses API the same schema goes under \`text.format\`. In strict mode, OpenAI requires every property to be listed in \`required\`. Model optional fields as nullable.

## Gemini: responseJsonSchema

\`\`\`json
{
  "generationConfig": {
    "responseMimeType": "application/json",
    "responseJsonSchema": { "type": "object", "properties": { "vendor": { "type": "string" } }, "required": ["vendor"] }
  }
}
\`\`\`

Gemini also has an older \`responseSchema\` field that takes an OpenAPI-style subset. \`responseJsonSchema\` accepts standard JSON Schema.

## Schema rules that work on every provider

1. **\`additionalProperties: false\`** on every object.
2. **List every field in \`required\`.** Make missing facts \`["string", "null"]\` rather than optional, so the model says "null" instead of inventing a value.
3. **Write a \`description\` per field.** The model reads it as an instruction ("ISO 4217 code, e.g. USD").
4. **Keep it flat.** Deep recursion, huge enums and exotic keywords are where provider support differs.
5. **Prefer \`enum\` over free text** for categories.

## Handle the failure cases

The schema guarantees the shape, not the outcome. Before you parse:

- **Check the stop reason.** \`max_tokens\` means the JSON may be truncated. A refusal may carry no JSON at all.
- **Validate business rules** (totals add up, dates are in range) after parsing. The model can still be wrong inside a valid shape.
- **Treat extracted values as untrusted input**, especially before they reach SQL, shell commands or HTML.

Open the structured output template and ask the workspace to "add a line_items array to the schema" or "convert this to the OpenAI response_format shape", then diff the result.`,
};
