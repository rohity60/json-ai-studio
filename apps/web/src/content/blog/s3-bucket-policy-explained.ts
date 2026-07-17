import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 's3-bucket-policy-explained',
    title: 'S3 Bucket Policy Explained, With Examples',
    description:
      'What an S3 bucket policy is, how it differs from an IAM policy, and a field-by-field walkthrough of Principal, Action, Resource and Condition — with copy-paste examples.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['aws', 's3', 'bucket-policy', 'json', 'security', 'reference'],
    readingTime: '5 min',
    aiSummary:
      'An S3 bucket policy is a resource-based JSON policy attached directly to a bucket. Unlike an IAM policy it always has a Principal (who it applies to). Each statement combines Effect, Principal, Action and Resource, optionally narrowed by Condition. The two most common bugs are a missing second ARN for object-level actions and a missing deny-insecure-transport statement.',
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-iam-readonly-policy'],
    relatedBlogs: [
      's3-bucket-policy-vs-iam-policy',
      's3-bucket-policy-generator',
      'iam-json-explained',
    ],
    faq: [
      {
        q: 'What is an S3 bucket policy?',
        a: 'A resource-based policy in JSON that you attach to an S3 bucket. It says who (Principal) can perform which actions (Action) on which resources (Resource), optionally under conditions.',
      },
      {
        q: 'Why does my bucket policy need two ARNs?',
        a: 'Bucket-level actions like s3:ListBucket act on the bucket ARN (arn:aws:s3:::name). Object-level actions like s3:GetObject act on the object ARN (arn:aws:s3:::name/*). Miss one and the action silently fails.',
      },
      {
        q: 'Does the Principal field matter?',
        a: 'Yes. A bucket policy is resource-based so it always needs a Principal. "*" means everyone (anonymous); an account or role ARN scopes it to a specific identity.',
      },
    ],
  },
  body: `An S3 bucket policy is a JSON document you attach directly to a bucket to control who can do what with it. It looks like an IAM policy but with one key addition: a **Principal**.

## The shape

\`\`\`json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPublicAssets",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-public-assets/*"
    }
  ]
}
\`\`\`

## Field by field

- **Version** — always \`"2012-10-17"\`. Not a date you edit.
- **Effect** — \`"Allow"\` or \`"Deny"\`. A Deny always wins over any Allow.
- **Principal** — *this is the S3-specific part.* Who the statement applies to. \`"*"\` = anyone on the internet. \`{ "AWS": "arn:aws:iam::111122223333:role/app" }\` scopes it to one identity.
- **Action** — the S3 API operations, e.g. \`s3:GetObject\`, \`s3:PutObject\`, \`s3:ListBucket\`. Wildcards like \`s3:*\` are allowed but rarely a good idea.
- **Resource** — the ARNs the actions apply to.
- **Condition** *(optional)* — tests that must be true, e.g. require HTTPS or a specific source.

## The two-ARN rule

The single most common bucket-policy bug: using one ARN for actions that need two.

- ❌ \`ListBucket\` on \`arn:aws:s3:::my-bucket/*\` — fails, list acts on the bucket, not objects.
- ✅ \`ListBucket\` on \`arn:aws:s3:::my-bucket\` **and** \`GetObject\` on \`arn:aws:s3:::my-bucket/*\`.

Bucket-level actions use the bare bucket ARN; object-level actions use \`/*\`.

## Always deny insecure transport

Any public or shared bucket should pair its Allow with a deny for plain HTTP:

\`\`\`json
{
  "Sid": "DenyInsecureTransport",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::my-public-assets",
    "arn:aws:s3:::my-public-assets/*"
  ],
  "Condition": { "Bool": { "aws:SecureTransport": "false" } }
}
\`\`\`

## Verify before you ship

Public read means *everyone* can fetch *every* object — never store secrets in such a bucket, and review with S3 Access Analyzer first.

Open the S3 bucket policy template in the workspace and ask "explain each statement" — the AI narrates every field against the values actually present, so you can see exactly what your policy grants.`,
};
