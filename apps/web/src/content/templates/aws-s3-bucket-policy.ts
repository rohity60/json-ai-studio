import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'aws-s3-bucket-policy',
    slug: 'aws-s3-bucket-policy',
    title: 'AWS S3 Bucket Policy — Secure Public Read',
    description:
      'An S3 bucket policy that allows public read of static assets while forcing HTTPS and blocking every other action — a common CDN/origin setup.',
    category: 'Cloud',
    provider: 'AWS',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['s3', 'aws', 'bucket-policy', 'security', 'https', 'cdn'],
    schemaVersion: '2012-10-17',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain each statement',
      'Restrict access to a CloudFront origin only',
      'Make this private instead of public',
      'Add a deny for unencrypted uploads',
    ],
    relatedTemplates: ['aws-iam-readonly-policy', 'aws-lambda-s3-event'],
    relatedBlogs: ['iam-json-explained', 'least-privilege-iam'],
    purpose:
      'Serve static files publicly over HTTPS while denying insecure transport and any write/delete action.',
    whenToUse:
      'A public assets bucket behind a CDN, a static website origin, or any bucket serving read-only files to anonymous users.',
    requiredFields: [
      'Version — policy language version',
      'Statement — the permission statements',
      'Principal — who the statement applies to ("*" = everyone)',
      'Resource — bucket and object ARNs',
    ],
    optionalFields: [
      'Sid — statement id',
      'Condition — e.g. aws:SecureTransport, aws:Referer, source VPC',
    ],
    bestPractices: [
      'Always pair a public-read Allow with a deny-insecure-transport statement.',
      'Prefer serving through CloudFront and locking the bucket to its OAI/OAC.',
      'Keep Block Public Access on unless the bucket genuinely must be public.',
    ],
    security: [
      'Public read means anyone on the internet can fetch every object — never store secrets here.',
      'The SecureTransport deny below blocks plain HTTP; keep it.',
      'Review with S3 Access Analyzer before shipping public policies.',
    ],
  },
  json: {
    Version: '2012-10-17',
    Statement: [
      {
        Sid: 'PublicReadGetObject',
        Effect: 'Allow',
        Principal: '*',
        Action: 's3:GetObject',
        Resource: 'arn:aws:s3:::my-public-assets/*',
      },
      {
        Sid: 'DenyInsecureTransport',
        Effect: 'Deny',
        Principal: '*',
        Action: 's3:*',
        Resource: [
          'arn:aws:s3:::my-public-assets',
          'arn:aws:s3:::my-public-assets/*',
        ],
        Condition: { Bool: { 'aws:SecureTransport': 'false' } },
      },
    ],
  },
};
