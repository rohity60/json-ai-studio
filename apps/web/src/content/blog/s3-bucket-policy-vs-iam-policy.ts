import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 's3-bucket-policy-vs-iam-policy',
    title: 'S3 Bucket Policy vs IAM Policy: Which One Do You Need?',
    description:
      'Bucket policies and IAM policies both grant S3 access but attach to different things and evaluate differently. When to use each, how they combine, and why a Deny in either one wins.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['aws', 's3', 'iam', 'bucket-policy', 'security', 'reference'],
    readingTime: '5 min',
    aiSummary:
      'An IAM policy is identity-based (attached to a user/role, no Principal) and answers "what can this identity do?". A bucket policy is resource-based (attached to a bucket, always has a Principal) and answers "who can touch this bucket?". Access is the union of allows across both, but any explicit Deny in either wins. Use IAM for your own principals, bucket policies for cross-account or anonymous access.',
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-iam-readonly-policy'],
    relatedBlogs: [
      's3-bucket-policy-explained',
      'what-is-an-iam-policy',
      'least-privilege-iam',
    ],
    faq: [
      {
        q: 'What is the core difference?',
        a: 'An IAM policy is identity-based: it attaches to a user, group or role and has no Principal. A bucket policy is resource-based: it attaches to the bucket and always names a Principal.',
      },
      {
        q: 'If both apply, which wins?',
        a: 'Access is the union of Allows across both, but an explicit Deny in either one always wins. For same-account access you only need an Allow in one of them.',
      },
      {
        q: 'When must I use a bucket policy?',
        a: 'For cross-account access and for anonymous/public access — those cases need a Principal, which only a resource-based policy has.',
      },
    ],
  },
  body: `Both an S3 bucket policy and an IAM policy can grant \`s3:GetObject\`. They are not interchangeable — they attach to different things and evaluate together.

## The one-line difference

- **IAM policy** — *identity-based.* Attached to a user, group or role. Has **no Principal** (the identity it attaches to *is* the principal). Answers: "what is this identity allowed to do?"
- **Bucket policy** — *resource-based.* Attached to the bucket. **Always has a Principal.** Answers: "who is allowed to touch this bucket?"

## Side by side

| | IAM policy | Bucket policy |
|---|---|---|
| Attaches to | User / group / role | The bucket |
| Has \`Principal\`? | No | Yes (required) |
| Good for | Your own principals | Cross-account, anonymous/public |
| Lives in | IAM | S3 |

## How they combine

For a request to succeed, AWS evaluates *both*:

1. Collect every applicable statement from IAM policies **and** the bucket policy.
2. If **any** statement has an explicit \`Deny\` → **denied**. Deny always wins.
3. Otherwise, if **any** statement has an \`Allow\` → **allowed**.
4. Otherwise → **denied** by default.

So for **same-account** access you only need an Allow in *one* of them. For **cross-account** access you generally need an Allow on *both* sides — the bucket policy trusts the other account, and that account's IAM lets its principal use S3.

## Which do I reach for?

- Granting *your own* role read access → **IAM policy**.
- A *different account* needs access → **bucket policy** (name their account/role as Principal) + their IAM.
- *Anonymous* public read → **bucket policy** with \`Principal: "*"\`.
- Blanket guardrail (deny non-HTTPS, deny outside a VPC) → **bucket policy** \`Deny\` — it covers every principal at once.

## Verify the combination, not just one file

Because a Deny in either policy wins, reading one file in isolation lies to you. Paste both into the workspace and ask "does this identity get GetObject on this bucket, and why?" — the AI walks the allow/deny evaluation across both documents.`,
};
