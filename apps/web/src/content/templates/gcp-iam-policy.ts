import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'gcp-iam-policy',
    slug: 'gcp-iam-policy',
    title: 'GCP IAM Policy Binding',
    description:
      'A Google Cloud IAM policy binding JSON granting a role to members, with an etag for safe concurrent updates — the shape returned by getIamPolicy.',
    category: 'Cloud',
    provider: 'Google Cloud',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['gcp', 'iam', 'security', 'policy', 'binding'],
    schemaVersion: '3',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain the bindings and roles',
      'Add a viewer role for a service account',
      'Add a conditional binding by resource',
      'Remove the owner binding',
    ],
    relatedTemplates: ['aws-iam-readonly-policy', 'azure-arm-template'],
    relatedBlogs: ['least-privilege-iam'],
    purpose:
      'Grant IAM roles to members on a GCP resource, as consumed by setIamPolicy / gcloud.',
    whenToUse:
      'Managing access on a project, bucket, or service via the IAM API or Terraform.',
    requiredFields: [
      'bindings — role-to-members mappings',
      'role — the IAM role, e.g. roles/storage.objectViewer',
      'members — the identities granted the role',
    ],
    optionalFields: [
      'etag — concurrency token from getIamPolicy',
      'version — policy schema version (3 for conditions)',
      'condition — CEL expression scoping a binding',
    ],
    bestPractices: [
      'Always read-modify-write with the returned etag to avoid clobbering.',
      'Prefer predefined roles over primitive owner/editor/viewer.',
      'Use conditions to time-box or resource-scope access.',
    ],
    security: [
      'allUsers / allAuthenticatedUsers make a resource public — avoid unless intended.',
      'Grant roles to groups, not individuals, for manageable access.',
      'Audit bindings with the Policy Analyzer regularly.',
    ],
  },
  json: {
    version: 3,
    etag: 'BwWWja0YfJA=',
    bindings: [
      {
        role: 'roles/storage.objectViewer',
        members: [
          'group:data-readers@example.com',
          'serviceAccount:etl@my-project.iam.gserviceaccount.com',
        ],
      },
      {
        role: 'roles/storage.objectAdmin',
        members: ['user:alice@example.com'],
        condition: {
          title: 'only-prod-bucket',
          expression:
            "resource.name.startsWith('projects/_/buckets/prod-assets')",
        },
      },
    ],
  },
};
