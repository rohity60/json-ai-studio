import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'what-is-an-iam-policy',
    title: 'What Is an AWS IAM Policy?',
    description:
      'A plain-English introduction to AWS IAM policies: what they are, the JSON they are written in, and how AWS evaluates them.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'security', 'beginner'],
    readingTime: '4 min',
    aiSummary:
      'An IAM policy is a JSON document that says who can do what to which AWS resources. AWS reads every matching policy and allows an action only if something explicitly allows it and nothing explicitly denies it.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['iam-json-explained', 'least-privilege-iam', 'common-iam-mistakes'],
    faq: [
      {
        q: 'Where do IAM policies get attached?',
        a: 'To identities (users, groups, roles) as identity-based policies, or to resources (like an S3 bucket) as resource-based policies.',
      },
      {
        q: 'Does an empty policy deny everything?',
        a: 'AWS denies by default. An action is only allowed when a policy explicitly allows it and no policy explicitly denies it.',
      },
    ],
  },
  body: `AWS Identity and Access Management (IAM) policies are how you say **who can do what** in your AWS account. Every policy is a JSON document, and AWS evaluates it every time a request is made.

## The mental model

A policy is a list of *statements*. Each statement answers three questions:

- **Effect** — Allow or Deny
- **Action** — which API operations (like \`s3:GetObject\`)
- **Resource** — which ARNs the actions apply to

When a principal (a user or role) makes a request, AWS gathers every policy that applies and evaluates them together.

## How AWS decides

The evaluation logic is simple to remember:

1. Start from an implicit **deny**.
2. If any matching statement says **Allow**, the action is allowed…
3. …unless any matching statement says **Deny**, which always wins.

So an explicit Deny beats every Allow. This is why a single deny statement is a powerful guardrail.

## A minimal example

\`\`\`json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
\`\`\`

This grants read access to objects in one bucket — nothing more.

## Where to go next

The hardest part of IAM is not the syntax, it is choosing the *right* actions and resources. Open the read-only policy template in the workspace and ask the AI to explain each statement, then tighten it to your own bucket names.`,
};
