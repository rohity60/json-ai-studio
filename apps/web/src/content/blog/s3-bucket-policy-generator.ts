import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 's3-bucket-policy-generator',
    title: 'Generating an S3 Bucket Policy from Plain English',
    description:
      'Skip the blank page and the AWS Policy Generator UI: describe the access you want in plain English, generate the S3 bucket policy JSON, then verify the Principal, ARNs and conditions.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['aws', 's3', 'bucket-policy', 'ai', 'generator', 'productivity'],
    readingTime: '4 min',
    aiSummary:
      'You can describe an S3 bucket policy in plain English and generate the JSON, but treat it as a first draft. Verify four things: the Principal is as narrow as intended, object-level actions carry the /* ARN, no wildcard slipped into Action, and a deny-insecure-transport statement is present. Start from a template and iterate with diffs.',
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-iam-readonly-policy'],
    relatedBlogs: [
      's3-bucket-policy-explained',
      'iam-policy-generator',
      'how-ai-helps-build-iam-policies',
    ],
    faq: [
      {
        q: 'Is a generated bucket policy safe to use as-is?',
        a: 'Treat it as a first draft. Verify the Principal, the ARNs and the conditions, then test in a non-production account before shipping.',
      },
      {
        q: 'What makes a good prompt?',
        a: 'Name the exact actions, the exact bucket, who the Principal is, and any conditions. "Allow s3:GetObject for a CloudFront OAC only on the assets-prod bucket, deny plain HTTP" beats "give public S3 access".',
      },
    ],
  },
  body: `Writing an S3 bucket policy by hand is fiddly, and the classic AWS Policy Generator UI still leaves you hand-editing ARNs. Generating it from a description is faster — as long as you verify the result.

## Describe the intent precisely

Vague prompts produce over-broad policies. Compare:

- ❌ "Give my bucket public access"
- ✅ "Allow \`s3:GetObject\` for anyone on \`assets-prod\` objects only, and deny any request over plain HTTP"

The second names the **action**, the **Principal**, the **resource**, and a **condition** — the four things an S3 policy actually needs.

## Start from a known-good shape

Rather than a blank editor, open the S3 bucket policy template and edit from there. You inherit a correct structure — both the bucket and object ARNs, a deny-insecure-transport guardrail — and only change the specifics.

## Verify four things

After generating, check:

1. **Principal** is as narrow as you meant (\`"*"\` is a big deal — that is the whole internet).
2. **Both ARNs** are present where object and bucket actions are mixed.
3. **No wildcard** crept into \`Action\` (\`s3:*\` on an Allow is almost never right).
4. A **deny-insecure-transport** statement is present.

## Iterate with diffs

Ask follow-ups like "restrict this to a CloudFront origin" or "make it private instead" and review each change as a side-by-side diff before accepting it. That review step is where correctness actually happens — the generator gets you 90% there, the diff gets you the last 10%.

Open the template, describe your case, and let the workspace generate and diff the policy for you.`,
};
