import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'least-privilege-iam',
    title: 'Least-Privilege IAM: A Practical Guide',
    description:
      'How to design IAM policies that grant the minimum access needed — scoping actions, resources and conditions instead of reaching for wildcards.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'security', 'least-privilege'],
    readingTime: '5 min',
    aiSummary:
      'Least privilege means granting only the actions and resources a role truly needs. Start from nothing, add specific actions on specific ARNs, add conditions, and review with Access Analyzer.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['what-is-an-iam-policy', 'iam-json-explained', 'common-iam-mistakes'],
    faq: [
      {
        q: 'Is "Action": "*" ever acceptable?',
        a: 'Rarely — mostly for break-glass admin roles protected by MFA. For workloads, always enumerate the specific actions.',
      },
      {
        q: 'How do I find the minimum actions a service needs?',
        a: 'Run it with CloudTrail on, then use IAM Access Analyzer to generate a policy from observed activity, and prune from there.',
      },
    ],
  },
  body: `Least privilege is the principle that a role should be able to do **exactly** what it needs and nothing more. It is the difference between a leaked key being a shrug and being a catastrophe.

## Start from zero

Do not start from an AWS managed policy like \`AmazonS3FullAccess\` and try to trim it. Start from an empty policy and add only what breaks when you run the workload.

## Scope three things

1. **Actions** — list specific operations, not \`s3:*\`.
2. **Resources** — name the exact ARNs, not \`"*"\`.
3. **Conditions** — constrain by region, tag, or source when you can.

\`\`\`json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::reports-prod/*",
  "Condition": {
    "StringEquals": { "aws:RequestedRegion": "us-east-1" }
  }
}
\`\`\`

This role can read report objects, in one bucket, in one region. Nothing else.

## Use deny as a guardrail

Because an explicit **Deny** always wins, a single deny statement can enforce an invariant across an account — for example, deny any S3 action over plain HTTP.

## Review, don't guess

- Turn on **CloudTrail** and let the workload run.
- Use **IAM Access Analyzer** to generate a policy from real activity.
- Prune generously — unused permissions are pure risk.

Paste your policy into the workspace and ask "remove unnecessary permissions" to get a tightened version you can diff against the original.`,
};
