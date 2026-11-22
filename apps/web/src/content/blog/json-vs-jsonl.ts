import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-vs-jsonl',
    title: 'JSON vs JSONL (JSON Lines): Differences, When to Use Each, and How to Convert',
    description:
      'JSON stores one value per file; JSONL stores one JSON value per line. Learn the differences, why JSONL wins for logs, streaming, big data and LLM batch or fine-tuning files, and how to convert between them with jq and Python.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['jsonl', 'json lines', 'ndjson', 'json vs jsonl', 'streaming', 'big data'],
    readingTime: '6 min',
    aiSummary:
      'A JSON file holds one root value, usually an array, so a parser must read the whole file. JSONL (JSON Lines, also called NDJSON) puts one complete JSON value on each line, separated by \\n, so files can be streamed, appended to and split without parsing everything. Use JSON for configs and API responses; use JSONL for logs, data exports, mongoimport/BigQuery loads, and LLM batch or fine-tuning datasets. Convert with jq -c ".[]" (JSON → JSONL) and jq -s "." (JSONL → JSON).',
    relatedTemplates: ['sample-json-data', 'sample-api-response'],
    relatedBlogs: ['sample-json-data-guide', 'json-vs-yaml', 'json-vs-toon', 'json-vs-jsonb'],
    faq: [
      {
        q: 'Is JSONL the same as NDJSON?',
        a: 'In practice, yes. Both mean newline-delimited JSON: one valid JSON value per line, UTF-8, separated by \\n. The file extensions are .jsonl and .ndjson.',
      },
      {
        q: 'Is a JSONL file valid JSON?',
        a: 'No. A JSONL file with more than one line has several root values, which a normal JSON parser rejects. Each individual line is valid JSON.',
      },
      {
        q: 'Can a JSONL line be pretty-printed over several lines?',
        a: 'No. Each record must be on a single line, with no raw newlines inside it. Newlines inside strings are escaped as \\n, which JSON serializers do automatically.',
      },
      {
        q: 'Why do LLM APIs use JSONL for batch and fine-tuning files?',
        a: 'Each line is one independent request or training example. The service can stream the file, process lines in parallel and report errors per line, which a single huge JSON array would not allow.',
      },
    ],
  },
  body: `Both formats use exactly the same JSON syntax. The only difference is how many values a file holds.

## The difference in one example

**JSON**: one root value, usually an array.

\`\`\`json
[
  { "id": 1, "event": "login", "user": "asha" },
  { "id": 2, "event": "purchase", "user": "daniel", "amount": 5998 }
]
\`\`\`

**JSONL**: one complete value per line, no enclosing array, no commas between records.

\`\`\`text
{"id": 1, "event": "login", "user": "asha"}
{"id": 2, "event": "purchase", "user": "daniel", "amount": 5998}
\`\`\`

## Comparison

| | JSON | JSONL |
|---|---|---|
| Root values per file | Exactly one | One per line |
| Read without loading everything | Hard (needs a streaming parser) | Easy: read line by line |
| Append a record | Rewrite the closing \`]\` | Write one more line |
| Split / parallelize | Must parse first | Split on newlines (\`split -l\`) |
| A corrupt record breaks | The whole file | Only that line |
| Pretty-printing | Allowed | Not allowed (one line per record) |
| Human readability | Good | OK for small records |
| Typical extension | \`.json\` | \`.jsonl\`, \`.ndjson\` |

## When to use JSON

- **Config files** (\`package.json\`, \`tsconfig.json\`, settings files): one document, edited by people.
- **API request and response bodies**: one value per HTTP message.
- **Small datasets** you want to read in an editor.

## When to use JSONL

- **Logs and event streams**: every log line is a record you can \`grep\`, \`tail -f\` and append to.
- **Large exports and imports**: MongoDB's \`mongoimport\` and BigQuery's newline-delimited JSON loads read one record per line.
- **LLM batch and fine-tuning files**: OpenAI and Anthropic batch inputs and most fine-tuning datasets are JSONL, one request or example per line.
- **Data pipelines**: Spark, DuckDB and pandas (\`lines=True\`) all read JSONL directly and can process it in chunks.

A rule of thumb: if the data is a **document**, use JSON. If it is a **stream of records**, use JSONL.

## Converting with jq

\`\`\`bash
# JSON array → JSONL
jq -c '.[]' employees.json > employees.jsonl

# JSONL → JSON array
jq -s '.' employees.jsonl > employees.json
\`\`\`

\`-c\` prints each value compactly on one line. \`-s\` (slurp) collects all lines into one array.

## Converting with Python

\`\`\`python
import json

# JSON → JSONL
with open("employees.json") as src, open("employees.jsonl", "w") as dst:
    for row in json.load(src):
        dst.write(json.dumps(row, ensure_ascii=False) + "\\n")

# Stream a JSONL file without loading it all
with open("events.jsonl") as f:
    for line in f:
        if line.strip():
            event = json.loads(line)
\`\`\`

With pandas: \`pd.read_json("events.jsonl", lines=True)\` and \`df.to_json("out.jsonl", orient="records", lines=True)\`.

## Common JSONL mistakes

- **Pretty-printing records.** A record spread over several lines breaks every JSONL reader.
- **Wrapping the file in \`[ ]\`** or adding commas between lines. That makes it neither valid JSON nor valid JSONL.
- **Windows line endings.** Most readers accept \`\\r\\n\`, but some strict tools do not. Write \`\\n\`.
- **A blank last line.** Usually fine, but skip empty lines when you parse.

## Related comparisons

- [JSON vs YAML](/blog/json-vs-yaml) for config files.
- [JSON vs TOON](/blog/json-vs-toon) for sending data to LLMs.
- [JSON vs JSONB](/blog/json-vs-jsonb) for storing JSON in PostgreSQL.
`,
};
