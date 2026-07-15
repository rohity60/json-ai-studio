import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'iam-json-explained',
    title: 'IAM Policy JSON Explained, Field by Field',
    description:
      'A field-by-field walkthrough of the IAM policy JSON structure: Version, Statement, Sid, Effect, Action, Resource, Principal and Condition.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'json', 'reference'],
    readingTime: '5 min',
    aiSummary:
      'Every IAM policy has a Version and a list of Statements. Each statement combines Effect, Action and Resource, optionally scoped by Principal and Condition. This post explains what each field means and the common mistakes for each.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['what-is-an-iam-policy', 'least-privilege-iam', 'common-iam-mistakes'],
    faq: [
      {
        q: 'What value should Version be?',
        a: 'Always "2012-10-17". It is the policy language version, not a date you should change.',
      },
      {
        q: 'Is Sid required?',
        a: 'No. Sid is an optional human-readable statement id. It is useful for readability and for referencing statements in tooling.',
      },
    ],
  },
  body: `An IAM policy looks intimidating until you know what each field does. Here is the whole vocabulary.

## Top level

- **Version** — the policy language version. Always \`"2012-10-17"\`. This is not a date you edit.
- **Statement** — an array of one or more permission statements. Order does not matter.

## Inside a statement

- **Sid** *(optional)* — a statement id, purely for humans and tooling.
- **Effect** — \`"Allow"\` or \`"Deny"\`. Deny always wins.
- **Action** — one or more API operations, like \`s3:GetObject\` or \`logs:*\`. Wildcards are allowed.
- **Resource** — the ARNs the actions apply to. \`"*"\` means every resource.
- **Principal** — *(resource-based policies only)* who the statement applies to.
- **Condition** *(optional)* — key/value tests that must be true, e.g. require HTTPS.

## A worked example

\`\`\`json
{
  "Sid": "ReadOneBucket",
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::my-app-data",
    "arn:aws:s3:::my-app-data/*"
  ]
}
\`\`\`

Note the **two ARNs**: \`ListBucket\` acts on the bucket itself, while \`GetObject\` acts on objects (the \`/*\`). Forgetting one of these is the single most common IAM bug.

## Conditions in one line

\`\`\`json
"Condition": { "Bool": { "aws:SecureTransport": "true" } }
\`\`\`

This restricts the statement to HTTPS requests only.

Open a real policy in the workspace and ask "explain each statement" — the AI narrates every field against the values actually present.`,
};
