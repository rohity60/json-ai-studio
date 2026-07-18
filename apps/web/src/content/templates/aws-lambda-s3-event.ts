import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'aws-lambda-s3-event',
    slug: 'aws-lambda-s3-event',
    title: 'AWS Lambda S3 Event Payload',
    description:
      'The exact event JSON AWS Lambda receives when an object is created in S3 — invaluable for writing and unit-testing handlers locally.',
    category: 'Cloud',
    provider: 'AWS',
    difficulty: 'beginner',
    estimatedReadTime: '4 min',
    tags: ['lambda', 'aws', 's3', 'event', 'serverless', 'testing'],
    schemaVersion: '1.0',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Change the bucket name to my-uploads',
      'Change this to an ObjectRemoved event',
      'Add a second record for another object',
      'Which fields does my handler actually need?',
    ],
    relatedTemplates: ['aws-s3-bucket-policy', 'aws-iam-readonly-policy'],
    relatedBlogs: ['iam-json-explained'],
    purpose:
      'Provide a realistic S3 "ObjectCreated:Put" event to drive local development and unit tests of a Lambda handler.',
    whenToUse:
      'When building an S3-triggered Lambda and you need a faithful sample event to invoke the function without deploying.',
    requiredFields: [
      'Records — the array of event records (S3 batches by object)',
      'eventName — the S3 event type, e.g. ObjectCreated:Put',
      's3.bucket.name — the source bucket',
      's3.object.key — the object key that triggered the event',
    ],
    optionalFields: [
      's3.object.size / eTag — object metadata',
      'requestParameters.sourceIPAddress — caller IP',
      'userIdentity.principalId — who put the object',
    ],
    bestPractices: [
      'Always iterate event.Records — a single invocation can carry several.',
      'URL-decode object keys (spaces arrive as "+").',
      'Treat delivery as at-least-once and make handlers idempotent.',
    ],
    security: [
      'Never trust object keys blindly — validate before using in paths or shell.',
      'Scope the Lambda execution role to the specific bucket/prefix.',
    ],
  },
  json: {
    Records: [
      {
        eventVersion: '2.1',
        eventSource: 'aws:s3',
        awsRegion: 'us-east-1',
        eventTime: '2026-07-15T12:00:00.000Z',
        eventName: 'ObjectCreated:Put',
        userIdentity: { principalId: 'AWS:AIDAEXAMPLE' },
        requestParameters: { sourceIPAddress: '203.0.113.10' },
        s3: {
          s3SchemaVersion: '1.0',
          configurationId: 'uploads-trigger',
          bucket: {
            name: 'my-app-uploads',
            arn: 'arn:aws:s3:::my-app-uploads',
          },
          object: {
            key: 'incoming/report-2026-07-15.csv',
            size: 20480,
            eTag: '9b2cf535f27731c974343645a3985328',
            sequencer: '00A1B2C3D4E5F6',
          },
        },
      },
    ],
  },
};
