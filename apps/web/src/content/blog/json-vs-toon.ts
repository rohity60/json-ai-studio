import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-vs-toon',
    title: 'JSON vs TOON for LLMs: Does Token-Oriented Object Notation Save Tokens?',
    description:
      'TOON (Token-Oriented Object Notation) is a compact, indentation-based encoding of JSON data aimed at LLM prompts. See the same data in both, where TOON saves tokens, where it does not, and why model outputs should stay JSON.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['toon', 'json vs toon', 'llm', 'tokens', 'prompt engineering'],
    readingTime: '6 min',
    aiSummary:
      'TOON (Token-Oriented Object Notation) re-encodes the JSON data model with YAML-like indentation and CSV-like tables: an array of uniform objects is written once as a header users[2]{id,name,role}: followed by one comma-separated row per item. That removes repeated keys, quotes and braces, so it can use noticeably fewer tokens than JSON for large uniform arrays. For deeply nested or irregular data the savings shrink or vanish. Use TOON for big tabular data going into a prompt; keep JSON (with structured outputs or JSON Schema) for model outputs, APIs and storage.',
    relatedTemplates: ['llm-structured-output', 'anthropic-messages-request', 'openai-chat-request', 'sample-json-data'],
    relatedBlogs: ['llm-structured-outputs-json', 'json-vs-yaml', 'json-vs-jsonl', 'llm-thinking-reasoning-config'],
    faq: [
      {
        q: 'What is TOON?',
        a: 'Token-Oriented Object Notation: an open format that encodes the same data as JSON (objects, arrays, strings, numbers, booleans, null) in a more compact text form, mainly to reduce tokens when passing data to a language model.',
      },
      {
        q: 'Does TOON replace JSON?',
        a: 'No. It is a prompt-side encoding. Your APIs, files and databases stay JSON; you convert to TOON just before putting data into a prompt, using a TOON library.',
      },
      {
        q: 'Should I ask the model to answer in TOON?',
        a: 'Usually not. Structured output features (JSON Schema enforced by the API) only produce JSON, and every downstream tool parses JSON. Ask for JSON output and use TOON, if at all, for large inputs.',
      },
      {
        q: 'How much does TOON save?',
        a: 'It depends on the shape of the data. Long arrays of objects with the same keys save the most because keys are written once. Small or deeply nested objects save little. Measure with your model\'s token counter on your real data before switching.',
      },
    ],
  },
  body: `Every key, quote and brace in a JSON prompt costs tokens. TOON (Token-Oriented Object Notation) is a format designed to send the same data in fewer of them.

## Same data, two encodings

**JSON** (pretty-printed):

\`\`\`json
{
  "users": [
    { "id": 1, "name": "Asha", "role": "admin" },
    { "id": 2, "name": "Daniel", "role": "editor" },
    { "id": 3, "name": "Mia", "role": "viewer" }
  ]
}
\`\`\`

**TOON**:

\`\`\`text
users[3]{id,name,role}:
  1,Asha,admin
  2,Daniel,editor
  3,Mia,viewer
\`\`\`

The header \`users[3]{id,name,role}\` declares the array length and the field names once. Each row is then just values. With 1,000 users, JSON repeats \`"id"\`, \`"name"\` and \`"role"\` 1,000 times; TOON writes them once.

## How TOON encodes other shapes

\`\`\`text
service: checkout
replicas: 3
env:
  LOG_LEVEL: info
  REGION: eu-west-1
tags[3]: payments,critical,eu
\`\`\`

- **Objects** use indentation and \`key: value\`, like YAML.
- **Arrays of primitives** go inline: \`tags[3]: a,b,c\`.
- **Arrays of uniform objects** become tables (the header + rows form above).
- **Strings** are quoted only when they need to be (commas, leading spaces, values that look like numbers or booleans).

## Where TOON helps and where it does not

| Data shape | Likely savings vs compact JSON |
|---|---|
| Long arrays of objects with identical keys (rows from a DB, logs, products) | Large |
| Mixed config-style objects | Small to moderate |
| Deeply nested or irregular objects (different keys per item) | Little or none; can be larger |
| A handful of short values | Negligible |

Two caveats:

1. **Compare against minified JSON**, not pretty-printed JSON. Removing whitespace alone (\`JSON.stringify(data)\` with no indent) recovers a lot of the gap.
2. **Accuracy matters more than tokens.** Models have seen enormous amounts of JSON. Test whether answers over TOON input are as accurate as over JSON for your task before you switch.

## Where JSON should stay

- **Model outputs.** Structured outputs (\`output_config.format\` on Claude, \`response_format\` on OpenAI) enforce a JSON Schema and only produce JSON. See [LLM structured outputs](/blog/llm-structured-outputs-json).
- **Tool calls.** Tool inputs and results are JSON on every major API.
- **Storage and APIs.** TOON is a transport for prompts, not a file format for your systems.

## A practical recipe

1. Keep data as JSON everywhere in your system.
2. For a large, table-like input (say, 500 order rows), encode it with a TOON library right before building the prompt.
3. Count tokens both ways with your provider's token-counting endpoint.
4. Run your eval on both encodings. Keep TOON only if it saves meaningful tokens **and** accuracy holds.
5. Ask the model to reply in JSON, ideally with an enforced schema.

## Alternatives worth trying first

- **Minify the JSON.** Often the biggest cheap win.
- **Drop fields** the model does not need.
- **CSV** for strictly flat tables. TOON's tables are close to CSV but also handle nesting.
- **Prompt caching** if the same large context is sent repeatedly; it cuts cost regardless of format.

## Related

- [JSON vs YAML](/blog/json-vs-yaml): TOON borrows YAML's indentation.
- [JSON vs JSONL](/blog/json-vs-jsonl): the format LLM batch and fine-tuning files use.
`,
};
