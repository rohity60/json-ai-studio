import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 's3-static-website-cloudfront',
    title: 'S3 Bucket Policies for Static Websites and CloudFront',
    description:
      'Two common S3 bucket policies compared: direct public read for a static website endpoint, and the modern CloudFront + OAC pattern that keeps the bucket private.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['aws', 's3', 'cloudfront', 'static-website', 'bucket-policy', 'cdn'],
    readingTime: '5 min',
    aiSummary:
      'For a static website you can either make the bucket publicly readable or, better, keep it private and let only CloudFront read it via Origin Access Control (OAC). The public-read policy uses Principal "*" plus a deny for non-HTTPS. The CloudFront policy scopes the Principal to the CloudFront service and a specific distribution ARN, so objects are never fetchable directly.',
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-lambda-s3-event'],
    relatedBlogs: [
      's3-bucket-policy-explained',
      's3-bucket-policy-generator',
      'least-privilege-iam',
    ],
    faq: [
      {
        q: 'Should I make the bucket public or use CloudFront?',
        a: 'Prefer CloudFront with Origin Access Control (OAC). The bucket stays private, only CloudFront can read it, and you get TLS, caching and WAF. Direct public read is simpler but exposes every object to the whole internet.',
      },
      {
        q: 'What replaced Origin Access Identity (OAI)?',
        a: 'Origin Access Control (OAC). OAI still works but OAC is the current recommendation — it supports SSE-KMS and all Regions. New setups should use OAC.',
      },
    ],
  },
  body: `"S3 bucket policy for static website" and "for CloudFront" are two different jobs. Here are both, and why the second is usually the right one.

## Option A — direct public read (static website endpoint)

The bucket serves objects to anyone. Simple, but every object is world-readable.

\`\`\`json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-site/*"
    },
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:::my-site", "arn:aws:s3:::my-site/*"],
      "Condition": { "Bool": { "aws:SecureTransport": "false" } }
    }
  ]
}
\`\`\`

You must also turn off the relevant Block Public Access settings — and accept that anyone can enumerate and fetch objects directly.

## Option B — CloudFront + OAC (keep the bucket private)

The modern pattern: the bucket is **private**, and only your CloudFront distribution can read it via **Origin Access Control (OAC)**. Users hit CloudFront, never S3 directly.

\`\`\`json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontServicePrincipal",
      "Effect": "Allow",
      "Principal": { "Service": "cloudfront.amazonaws.com" },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-site/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::111122223333:distribution/E1XXXXXXXXXXXX"
        }
      }
    }
  ]
}
\`\`\`

The Principal is the CloudFront **service**, and the \`SourceArn\` condition locks it to *one* distribution — so even other CloudFront distributions can't read the bucket. Block Public Access stays fully **on**.

## Which to pick

- Prototype / throwaway → Option A is fine.
- Anything real → **Option B**. You get TLS, caching, WAF, and no directly-reachable objects. Use OAC, not the older Origin Access Identity (OAI).

## Tweak it safely

Open the S3 bucket policy template and ask "convert this to a CloudFront OAC origin for distribution E123…" — the workspace rewrites the Principal and condition and shows you the diff before you apply it.`,
};
