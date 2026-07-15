import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'iam-policy-generator',
    title: 'Generating IAM Policies from Plain English',
    description:
      'How to go from "let this service read one S3 bucket" to a correct, least-privilege IAM policy JSON — and how to verify what you generated.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'ai', 'productivity'],
    readingTime: '4 min',
    aiSummary:
      'You can describe the access you want in plain English and generate the IAM JSON, but you must verify it: check the actions are minimal, the ARNs are specific, and no wildcard slipped in. Start from a template and iterate.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['least-privilege-iam', 'common-iam-mistakes', 'how-ai-helps-build-iam-policies'],
    faq: [
      {
        q: 'Can I trust a generated policy as-is?',
        a: 'Treat it as a first draft. Verify the actions are the minimum needed and the ARNs are specific, then test in a non-production account.',
      },
      {
        q: 'What is a good starting prompt?',
        a: 'Be concrete: name the service, the exact operations, and the exact resource, e.g. "allow read-only GetObject on the reports-prod bucket only".',
      },
    ],
  },
  body: `Writing IAM by hand is error-prone; generating it from a description is faster — if you verify the result.

## Describe the intent precisely

Vague prompts produce vague (over-broad) policies. Compare:

- ❌ "Give my app S3 access"
- ✅ "Allow \`s3:GetObject\` and \`s3:ListBucket\` on the \`reports-prod\` bucket only, over HTTPS"

The second names the **actions**, the **resource**, and a **condition** — exactly the three things least privilege needs.

## Start from a known-good shape

Rather than a blank page, open the read-only policy template and edit from there. You inherit a correct structure (both bucket and object ARNs, a deny-insecure-transport guardrail) and only change the specifics.

## Always verify

After generating, check three things:

1. **No wildcards** crept into Action or Resource.
2. **Both ARNs** are present where S3 needs them.
3. The policy **denies** what it should (HTTP, wrong region).

## Iterate with diffs

Ask follow-ups like "restrict this to us-east-1" or "remove write permissions" and review each change as a side-by-side diff before accepting it. That review step is where correctness actually happens.

Open the template, describe your case, and let the workspace generate and diff the policy for you.`,
};
