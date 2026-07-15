import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'common-iam-mistakes',
    title: 'Common IAM Policy Mistakes (and How to Fix Them)',
    description:
      'The IAM mistakes that bite everyone: wildcard actions, missing bucket ARNs, confused deputy conditions, and forgetting that Deny always wins.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'security', 'pitfalls'],
    readingTime: '5 min',
    aiSummary:
      'The frequent IAM errors are: wildcard actions/resources, only listing the object ARN and not the bucket ARN, over-broad Principal in resource policies, and misunderstanding that an explicit Deny overrides every Allow.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['iam-json-explained', 'least-privilege-iam', 'what-is-an-iam-policy'],
    faq: [
      {
        q: 'Why does my S3 ListBucket call fail even though GetObject works?',
        a: 'ListBucket acts on the bucket ARN (arn:aws:s3:::bucket), while GetObject acts on objects (…/*). You usually need both ARNs.',
      },
      {
        q: 'I added an Allow but access is still denied. Why?',
        a: 'Something is explicitly denying it — a Deny always wins over an Allow. Check SCPs, permission boundaries, and other statements.',
      },
    ],
  },
  body: `Most IAM pain comes from a short list of repeat offenders. Here they are.

## 1. Wildcards everywhere

\`"Action": "*"\` on \`"Resource": "*"\` is admin access. It sneaks into policies "just to get it working" and never gets removed. Enumerate specific actions and ARNs instead.

## 2. Forgetting the bucket ARN

S3 has two ARN shapes:

- the **bucket**: \`arn:aws:s3:::my-bucket\`
- the **objects**: \`arn:aws:s3:::my-bucket/*\`

\`ListBucket\` needs the first; \`GetObject\` needs the second. List both or you will get mysterious \`AccessDenied\` errors.

## 3. Assuming Allow is enough

An explicit **Deny** always overrides an Allow. If access fails despite an Allow, hunt for a Deny — often in a Service Control Policy or permission boundary, not the policy you are editing.

## 4. Over-broad Principal

In resource-based policies, \`"Principal": "*"\` means *the entire internet*. Combine it with a \`Condition\` (source account, VPC, or org id) or scope it to specific role ARNs.

## 5. Skipping HTTPS enforcement

Add a deny for insecure transport to any bucket that matters:

\`\`\`json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": ["arn:aws:s3:::b", "arn:aws:s3:::b/*"],
  "Condition": { "Bool": { "aws:SecureTransport": "false" } }
}
\`\`\`

## Fix it fast

Load your policy into the workspace and ask "find and fix problems". The AI flags these exact issues and proposes a corrected version you can review as a diff.`,
};
