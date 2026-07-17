import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 's3-select-deprecated-alternatives',
    title: "S3 Select Is Deprecated — Here's How to Query Your JSON Instead",
    description:
      'AWS is phasing out S3 Select. If you ran SQL over JSON or CSV objects in a bucket, here are the modern alternatives — Athena, S3 Object Lambda, and client-side querying — and how to pick.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['aws', 's3', 's3-select', 'json', 'query', 'athena', 'migration'],
    readingTime: '5 min',
    aiSummary:
      'S3 Select (SQL over a single S3 object) is deprecated and closed to new customers. Replacements depend on scale: Amazon Athena for SQL across many objects, S3 Object Lambda to transform objects on GET, and client-side querying (download + jq/DuckDB) for a single small JSON or CSV. For shaping one JSON config the simplest path is to pull the object and query it locally.',
    relatedTemplates: ['aws-s3-bucket-policy', 'openapi-spec'],
    relatedBlogs: [
      's3-bucket-policy-explained',
      'openapi-json-explained',
      'how-ai-helps-build-iam-policies',
    ],
    faq: [
      {
        q: 'Is S3 Select really deprecated?',
        a: 'Yes. AWS has closed S3 Select (and S3 Glacier Select) to new customers and points existing users to Amazon Athena and other services. New code should not depend on the SelectObjectContent API.',
      },
      {
        q: 'What is the closest replacement for querying one object?',
        a: 'Download the object and query it locally — jq for JSON, or DuckDB, which runs SQL directly over a JSON/CSV/Parquet file. For querying across many objects at scale, use Amazon Athena.',
      },
    ],
  },
  body: `If you searched "S3 Select alternative" or "S3 Select deprecated", the news is real: AWS is phasing out **S3 Select**, the feature that let you run a SQL \`SELECT\` against a single S3 object via the \`SelectObjectContent\` API. It is closed to new customers, and existing users are pointed elsewhere. Here is where "elsewhere" is.

## What S3 Select did

One API call ran SQL over *one* object (JSON, CSV or Parquet) and returned only the matching rows — handy for pulling a slice out of a big file without downloading it whole.

\`\`\`sql
SELECT s.name FROM S3Object[*] s WHERE s.active = true
\`\`\`

## The alternatives, by scale

**1. Amazon Athena — SQL across many objects.** Serverless, standard SQL, queries a whole prefix or table at once (backed by the Glue catalog). This is the intended replacement when you were using S3 Select at any real scale. You pay per data scanned, so partition and use columnar formats (Parquet) to keep costs down.

**2. S3 Object Lambda — transform on GET.** If the goal was "return a filtered/reshaped version of the object to the caller", an Object Lambda Access Point runs your function on each GET and returns the transformed bytes. Good when the *consumer* should keep calling a GET-like API.

**3. Client-side querying — one small object.** For a single JSON or CSV that fits in memory, just download it and query locally:

- \`jq\` for JSON filtering/reshaping.
- **DuckDB** to run real SQL directly over a JSON/CSV/Parquet file — the closest single-file feel to old S3 Select.

\`\`\`bash
aws s3 cp s3://my-bucket/data.json - | jq '[.[] | select(.active == true) | .name]'
\`\`\`

## How to choose

| Situation | Use |
|---|---|
| SQL across many objects, at scale | **Athena** |
| Reshape objects for callers on GET | **S3 Object Lambda** |
| One small JSON/CSV, ad-hoc | **Download + jq / DuckDB** |

## Shaping one JSON config

If you were only using S3 Select to pull and tidy a single JSON config, the client-side path is simplest — and you don't need SQL at all. Pull the object, drop it into the workspace, and describe the slice you want in plain English ("keep only active entries, sort by name"). The AI reshapes the JSON and shows you the diff, no query language required.`,
};
