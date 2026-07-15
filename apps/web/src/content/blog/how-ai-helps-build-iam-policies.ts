import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'how-ai-helps-build-iam-policies',
    title: 'How AI Helps You Build Safer IAM Policies',
    description:
      'AI is most useful for IAM not as a generator but as an explainer and reviewer — narrating what a policy does and catching over-broad grants before they ship.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['aws', 'iam', 'ai', 'security', 'review'],
    readingTime: '4 min',
    aiSummary:
      'AI shines at explaining an existing IAM policy in plain English and reviewing it for over-broad permissions. Use it to understand, tighten and diff policies — with a human approving each change.',
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-s3-bucket-policy'],
    relatedBlogs: ['iam-policy-generator', 'least-privilege-iam', 'common-iam-mistakes'],
    faq: [
      {
        q: 'Should AI have write access to my AWS account?',
        a: 'No. Use it to draft and review JSON; a human applies the change through your normal, audited deployment path.',
      },
      {
        q: 'What is the safest way to use AI for IAM?',
        a: 'Explain first, edit second, and review every change as a diff before accepting. Keep a human in the approval loop.',
      },
    ],
  },
  body: `The riskiest IAM policies are the ones nobody fully understands. That is exactly where AI helps.

## Explain before you edit

Paste a policy and ask "explain each statement". Getting a plain-English narration of what a policy *actually* grants — against the specific ARNs and actions present — catches surprises far faster than reading raw JSON.

## Review for over-broad access

Ask "what could this policy do that it probably shouldn't?" AI is good at spotting:

- wildcard actions and resources
- a \`Principal\` that is wider than intended
- missing HTTPS/region conditions

## Edit in small, reviewable steps

Instead of rewriting a policy in one shot, make targeted changes:

- "restrict this to one bucket"
- "remove write permissions"
- "add a deny for unencrypted transport"

Each request produces a **diff** you can inspect and accept or reject line by line.

## Keep the human in the loop

AI drafts and explains; a person approves. The JSON is applied through your normal, audited pipeline — never by handing an assistant credentials to your account.

## Try it

Open the read-only IAM template, ask the workspace to explain it, then tighten it to your resources. You will understand the policy *and* end up with a smaller blast radius.`,
};
