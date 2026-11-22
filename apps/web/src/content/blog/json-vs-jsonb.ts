import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'json-vs-jsonb',
    title: 'JSON vs JSONB in PostgreSQL: Differences, Indexing and Which to Use',
    description:
      'PostgreSQL has two JSON column types. json stores the exact text; jsonb stores a parsed binary form that can be indexed. Compare storage, key order, duplicate keys, operators and GIN indexes, with copy-ready SQL.',
    updatedAt: '2026-11-22',
    author: 'JSON AI Studio',
    tags: ['jsonb', 'postgresql', 'json vs jsonb', 'gin index', 'database'],
    readingTime: '7 min',
    aiSummary:
      'In PostgreSQL, json stores the input text verbatim (whitespace, key order and duplicate keys preserved) and re-parses it on every access. jsonb stores a decomposed binary form: whitespace is dropped, key order is not preserved, and only the last duplicate key is kept. jsonb is slightly slower to insert but much faster to query, and supports containment (@>), key-existence (?, ?|, ?&) operators and GIN indexes. Use jsonb by default; use json only when you must keep the exact original text.',
    relatedTemplates: ['mongodb-schema-validation', 'json-schema', 'sample-json-data'],
    relatedBlogs: ['json-vs-jsonl', 'json-schema-guide', 'sample-json-data-guide'],
    faq: [
      {
        q: 'Should I use json or jsonb in PostgreSQL?',
        a: 'jsonb for almost everything. Choose json only if you must return the document exactly as it was sent, including whitespace, key order and duplicate keys (for example an audit log of raw webhook payloads).',
      },
      {
        q: 'What is the difference between -> and ->>?',
        a: '-> returns the value as json/jsonb (so you can keep navigating), ->> returns it as text. data->\'address\'->>\'city\' gets the city as text.',
      },
      {
        q: 'Can I index a jsonb column?',
        a: 'Yes. A GIN index on the whole column speeds up @>, ?, ?| and ?& queries. For one frequently filtered field, a B-tree expression index on (data->>\'field\') is smaller and faster.',
      },
      {
        q: 'Does jsonb keep key order?',
        a: 'No. jsonb stores keys in its own internal order, and duplicate keys collapse to the last one. If key order matters to you, either use json or keep an explicit array.',
      },
    ],
  },
  body: `PostgreSQL has two column types for JSON. They accept the same input but store it very differently.

## The short version

| | \`json\` | \`jsonb\` |
|---|---|---|
| Stored as | Exact input text | Parsed binary |
| Whitespace | Preserved | Removed |
| Key order | Preserved | Not preserved |
| Duplicate keys | All kept | Last one wins |
| Insert speed | Faster (just validates) | Slightly slower (parses and converts) |
| Query speed | Re-parses on every access | Fast |
| Containment / existence operators | No | \`@>\`, \`<@\`, \`?\`, \`?\\|\`, \`?&\` |
| GIN indexing | No | Yes |
| Equality comparison | No | Yes |

Use \`jsonb\` unless you need the exact original text.

## See the difference

\`\`\`sql
SELECT '{"b": 1,  "a": 2, "a": 3}'::json  AS j,
       '{"b": 1,  "a": 2, "a": 3}'::jsonb AS jb;
\`\`\`

\`\`\`text
j  | {"b": 1,  "a": 2, "a": 3}
jb | {"a": 3, "b": 1}
\`\`\`

\`json\` returns the text unchanged. \`jsonb\` drops whitespace, reorders keys and keeps only the last \`"a"\`.

## A jsonb table

\`\`\`sql
CREATE TABLE employees (
  id   bigint PRIMARY KEY,
  data jsonb NOT NULL
);

INSERT INTO employees VALUES
  (1001, '{"name": "Asha Rao", "department": "Engineering",
           "skills": ["go", "kubernetes"], "address": {"city": "Bengaluru"}}'),
  (1002, '{"name": "Daniel Okafor", "department": "Engineering",
           "skills": ["typescript"], "address": {"city": "Lagos"}}');
\`\`\`

## Querying

\`\`\`sql
-- Read a field as text
SELECT data->>'name' FROM employees;

-- Navigate nested objects
SELECT data->'address'->>'city' FROM employees;
SELECT data #>> '{address,city}' FROM employees;

-- Containment: employees in Engineering who know Go
SELECT id FROM employees
WHERE data @> '{"department": "Engineering", "skills": ["go"]}';

-- Key existence
SELECT id FROM employees WHERE data ? 'manager';

-- SQL/JSON path
SELECT jsonb_path_query(data, '$.skills[*]') FROM employees;
\`\`\`

## Updating

\`\`\`sql
-- Set one nested field
UPDATE employees
SET data = jsonb_set(data, '{address,city}', '"Mumbai"')
WHERE id = 1001;

-- Merge fields (right side wins)
UPDATE employees SET data = data || '{"isActive": true}';

-- Remove a key
UPDATE employees SET data = data - 'manager';
\`\`\`

## Indexing

\`\`\`sql
-- Whole-document GIN index: speeds up @>, ?, ?|, ?&
CREATE INDEX employees_data_gin ON employees USING gin (data);

-- Smaller GIN index that only supports @> (and jsonpath @? / @@)
CREATE INDEX employees_data_path ON employees USING gin (data jsonb_path_ops);

-- One hot field: a plain B-tree expression index
CREATE INDEX employees_department ON employees ((data->>'department'));
\`\`\`

Filters must use the same operator or expression the index was built for. \`WHERE data->>'department' = 'Engineering'\` uses the expression index, not the GIN index.

## When json is the right choice

- You store **raw webhook or API payloads** and must reproduce them byte for byte, for example to verify a signature.
- You only ever **store and return** the document and never query inside it.

## Design tips

- Put fields you filter, join or sort on in **real columns**; keep jsonb for the flexible remainder.
- Add a \`CHECK\` constraint (or validate with JSON Schema in the application) so bad shapes do not sneak in.
- Very large jsonb values are TOASTed and compressed; updating one key rewrites the whole value, so avoid huge, frequently updated documents.

## Related

- [JSON Schema guide](/blog/json-schema-guide) for validating documents before they reach the database.
- [JSON vs JSONL](/blog/json-vs-jsonl) for bulk loading with \`COPY\` or import tools.
`,
};
