import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'aws-iam-readonly-policy',
    slug: 'aws-iam-readonly-policy',
    title: 'AWS IAM Read-only Policy',
    description:
      'A least-privilege IAM policy granting read-only access to S3 and CloudWatch logs — a safe starting point for auditors, dashboards and monitoring roles.',
    category: 'Cloud',
    provider: 'AWS',
    difficulty: 'beginner',
    estimatedReadTime: '4 min',
    tags: ['iam', 'aws', 'security', 'policy', 's3', 'read-only'],
    schemaVersion: '2012-10-17',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain each statement',
      'Restrict this to a single S3 bucket',
      'Add read access to DynamoDB',
      'Remove unnecessary permissions',
    ],
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-lambda-s3-event'],
    relatedBlogs: [
      'what-is-an-iam-policy',
      'iam-json-explained',
      'least-privilege-iam',
      'common-iam-mistakes',
    ],
    purpose:
      'Grant read-only visibility into S3 objects and CloudWatch logs without any ability to modify or delete resources.',
    whenToUse:
      'Attach to auditor roles, read-only dashboards, monitoring tools, or a support engineer who needs to inspect but never change infrastructure.',
    requiredFields: [
      'Version — the policy language version, always "2012-10-17"',
      'Statement — one or more permission statements',
      'Effect — "Allow" or "Deny"',
      'Action — the API operations the statement covers',
      'Resource — the ARNs the actions apply to',
    ],
    optionalFields: [
      'Sid — a human-readable statement id',
      'Condition — key/value constraints (e.g. restrict by IP or region)',
    ],
    bestPractices: [
      'Prefer explicit resource ARNs over "*" wherever possible.',
      'Split unrelated permissions into separate statements with Sids.',
      'Use Conditions to scope access by region, tag or source IP.',
    ],
    security: [
      'Read-only still exposes data — S3 GetObject can read sensitive files.',
      'Avoid "Resource": "*" in production; scope to named buckets/log groups.',
      'Pair with MFA and least-privilege trust policies on the role itself.',
    ],
  },
  json: {
    Version: '2012-10-17',
    Statement: [
      {
        Sid: 'ReadS3Objects',
        Effect: 'Allow',
        Action: ['s3:GetObject', 's3:ListBucket'],
        Resource: [
          'arn:aws:s3:::my-app-data',
          'arn:aws:s3:::my-app-data/*',
        ],
      },
      {
        Sid: 'ReadCloudWatchLogs',
        Effect: 'Allow',
        Action: [
          'logs:GetLogEvents',
          'logs:DescribeLogGroups',
          'logs:DescribeLogStreams',
        ],
        Resource: 'arn:aws:logs:*:*:log-group:/aws/my-app/*',
      },
    ],
  },
};
