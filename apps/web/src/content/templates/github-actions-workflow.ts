import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'github-actions-workflow',
    slug: 'github-actions-workflow',
    title: 'GitHub Actions CI Workflow (JSON view)',
    description:
      'A GitHub Actions CI workflow — checkout, setup, install, test — expressed as JSON for programmatic editing before converting back to workflow YAML.',
    category: 'CI/CD',
    provider: 'GitHub Actions',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['github-actions', 'ci', 'cd', 'workflow', 'automation'],
    schemaVersion: '1',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a step to upload build artifacts',
      'Add a job that builds a Docker image',
      'Run tests on Node 18 and 20 in a matrix',
      'Cache npm dependencies',
    ],
    relatedTemplates: ['jenkins-pipeline', 'kubernetes-deployment'],
    relatedBlogs: [],
    purpose:
      'Define an automated CI pipeline that runs on push and pull request to build and test the project.',
    whenToUse:
      'Editing a workflow programmatically (linting, templating, bulk changes) before serializing back to `.github/workflows/*.yml`.',
    requiredFields: [
      'on — the events that trigger the workflow',
      'jobs — the named jobs to run',
      'runs-on — the runner image for each job',
      'steps — the ordered actions/commands in a job',
    ],
    optionalFields: [
      'name — human-readable workflow name',
      'strategy.matrix — run a job across parameter combinations',
      'env — environment variables',
    ],
    bestPractices: [
      'Pin third-party actions to a full commit SHA, not a floating tag.',
      'Use a matrix to test across runtime versions.',
      'Cache dependencies to speed up runs.',
    ],
    security: [
      'Give GITHUB_TOKEN the least permissions the job needs.',
      'Never echo secrets; reference them via ${{ secrets.NAME }}.',
      'Treat pull_request_target and self-hosted runners as high-risk.',
    ],
  },
  json: {
    name: 'CI',
    on: {
      push: { branches: ['main'] },
      pull_request: {},
    },
    permissions: { contents: 'read' },
    jobs: {
      test: {
        'runs-on': 'ubuntu-latest',
        steps: [
          { uses: 'actions/checkout@v4' },
          {
            uses: 'actions/setup-node@v4',
            with: { 'node-version': '20', cache: 'npm' },
          },
          { run: 'npm ci' },
          { run: 'npm test' },
        ],
      },
    },
  },
};
