import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'jenkins-pipeline',
    slug: 'jenkins-pipeline',
    title: 'Jenkins Pipeline Definition (JSON)',
    description:
      'A JSON description of a Jenkins CI pipeline — parameters, ordered stages and steps — for tools that generate Jenkinsfiles from structured data.',
    category: 'CI/CD',
    provider: 'Jenkins',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['jenkins', 'ci', 'cd', 'pipeline', 'automation'],
    schemaVersion: '1',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain this pipeline definition',
      'Add a deploy stage after test',
      'Add a boolean parameter to skip tests',
      'Run the build and test stages in parallel',
    ],
    relatedTemplates: ['github-actions-workflow'],
    relatedBlogs: [],
    purpose:
      'Model a Jenkins declarative pipeline as JSON so it can be generated, linted, or transformed before emitting a Jenkinsfile.',
    whenToUse:
      'Programmatically authoring Jenkins pipelines, or storing pipeline shape in a database/UI before rendering Groovy.',
    requiredFields: [
      'agent — where the pipeline runs',
      'stages — the ordered list of build stages',
      'name + steps — each stage’s label and commands',
    ],
    optionalFields: [
      'parameters — build-time inputs',
      'environment — variables available to steps',
      'post — actions on success/failure/always',
    ],
    bestPractices: [
      'Keep stages small and named for readability in the UI.',
      'Fail fast — put quick checks (lint) before slow ones (integration).',
      'Store credentials in Jenkins Credentials, referenced by ID.',
    ],
    security: [
      'Never inline secrets; use the credentials() binding by ID.',
      'Restrict which agents/nodes a sensitive pipeline can run on.',
      'Avoid interpolating untrusted input into shell steps.',
    ],
  },
  json: {
    agent: 'any',
    parameters: [
      { type: 'boolean', name: 'RUN_TESTS', defaultValue: true },
    ],
    environment: { CI: 'true' },
    stages: [
      { name: 'Build', steps: ['npm ci', 'npm run build'] },
      {
        name: 'Test',
        when: "params.RUN_TESTS == true",
        steps: ['npm test'],
      },
      {
        name: 'Deploy',
        when: "branch == 'main'",
        steps: ['./deploy.sh production'],
      },
    ],
    post: {
      always: ['echo "pipeline finished"'],
      failure: ['echo "notify the team"'],
    },
  },
};
