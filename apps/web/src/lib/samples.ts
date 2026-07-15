/** Built-in sample JSONs for zero-friction onboarding.
 *
 *  First-time visitors rarely have a JSON file at hand — each sample is a
 *  realistic document they can load with one click (studio empty state,
 *  UploadPanel, or a /studio?sample=<id> deep link from the landing page).
 *  `prompts` seed the ChatPanel suggestion chips so the first AI edit is
 *  one tap away.
 */

export type Sample = {
  id: string;
  label: string;
  description: string;
  json: Record<string, any>;
  prompts: string[];
};

export const SAMPLES: Sample[] = [
  {
    id: 'package',
    label: 'package.json',
    description: 'Node.js project manifest with scripts and dependencies',
    json: {
      name: 'acme-web',
      version: '1.4.2',
      private: true,
      scripts: {
        dev: 'next dev',
        build: 'next build',
        start: 'next start',
        lint: 'eslint .',
      },
      dependencies: {
        next: '^15.4.0',
        react: '^19.0.0',
        'react-dom': '^19.0.0',
        zod: '^3.23.8',
      },
      devDependencies: {
        eslint: '^9.0.0',
        typescript: '^5.6.0',
      },
      engines: { node: '>=20' },
    },
    prompts: [
      'Add a test script using vitest',
      'Bump react and react-dom to ^19.1.0',
      'Add an "engines.npm" requirement of ">=10"',
      'Move zod to devDependencies',
    ],
  },
  {
    id: 'kubernetes',
    label: 'Kubernetes Deployment',
    description: 'Deployment manifest with probes and resource limits',
    json: {
      apiVersion: 'apps/v1',
      kind: 'Deployment',
      metadata: {
        name: 'checkout-service',
        labels: { app: 'checkout', tier: 'backend' },
      },
      spec: {
        replicas: 2,
        selector: { matchLabels: { app: 'checkout' } },
        template: {
          metadata: { labels: { app: 'checkout' } },
          spec: {
            containers: [
              {
                name: 'checkout',
                image: 'registry.acme.io/checkout:v1.8.0',
                ports: [{ containerPort: 8080 }],
                env: [
                  { name: 'LOG_LEVEL', value: 'info' },
                  { name: 'DB_HOST', value: 'postgres.internal' },
                ],
                resources: {
                  requests: { cpu: '250m', memory: '256Mi' },
                  limits: { cpu: '500m', memory: '512Mi' },
                },
                readinessProbe: {
                  httpGet: { path: '/healthz', port: 8080 },
                  initialDelaySeconds: 5,
                },
              },
            ],
          },
        },
      },
    },
    prompts: [
      'Scale replicas to 5',
      'Change the image tag to v2.0.0',
      'Add a liveness probe matching the readiness probe',
      'Set LOG_LEVEL to debug',
    ],
  },
  {
    id: 'openapi',
    label: 'OpenAPI Spec',
    description: 'REST API definition with two endpoints',
    json: {
      openapi: '3.1.0',
      info: { title: 'Orders API', version: '2.1.0' },
      servers: [{ url: 'https://api.acme.io/v2' }],
      paths: {
        '/orders': {
          get: {
            summary: 'List orders',
            parameters: [
              {
                name: 'status',
                in: 'query',
                schema: { type: 'string', enum: ['pending', 'shipped', 'delivered'] },
              },
            ],
            responses: { '200': { description: 'A list of orders' } },
          },
          post: {
            summary: 'Create an order',
            responses: { '201': { description: 'Order created' } },
          },
        },
        '/orders/{orderId}': {
          get: {
            summary: 'Get one order',
            parameters: [
              { name: 'orderId', in: 'path', required: true, schema: { type: 'string' } },
            ],
            responses: {
              '200': { description: 'The order' },
              '404': { description: 'Not found' },
            },
          },
        },
      },
    },
    prompts: [
      'Add a DELETE operation for /orders/{orderId}',
      'Add a 401 response to every operation',
      'Add a "cancelled" value to the status enum',
      'Bump the API version to 2.2.0',
    ],
  },
  {
    id: 'github-actions',
    label: 'GitHub Actions CI',
    description: 'Workflow that lints, tests and builds on push',
    json: {
      name: 'CI',
      on: { push: { branches: ['main'] }, pull_request: {} },
      jobs: {
        test: {
          'runs-on': 'ubuntu-latest',
          steps: [
            { uses: 'actions/checkout@v4' },
            { uses: 'actions/setup-node@v4', with: { 'node-version': 20, cache: 'npm' } },
            { run: 'npm ci' },
            { run: 'npm run lint' },
            { run: 'npm test' },
            { run: 'npm run build' },
          ],
        },
      },
    },
    prompts: [
      'Add a matrix for node versions 20 and 22',
      'Add a lint job that runs in parallel',
      'Cache the build output',
      'Run tests on pull requests only',
    ],
  },
  {
    id: 'feature-flags',
    label: 'Feature Flags',
    description: 'App config with rollout percentages and targeting',
    json: {
      service: 'web-app',
      environment: 'production',
      flags: {
        newCheckout: { enabled: true, rollout: 25, audiences: ['beta-users'] },
        darkMode: { enabled: true, rollout: 100 },
        aiAssistant: { enabled: false, rollout: 0, audiences: ['internal'] },
        priceExperiments: {
          enabled: true,
          rollout: 50,
          variants: { control: 0.5, testA: 0.25, testB: 0.25 },
        },
      },
      refreshIntervalSeconds: 300,
    },
    prompts: [
      'Roll out newCheckout to 100%',
      'Enable aiAssistant for beta-users too',
      'Disable darkMode and set rollout to 0',
      'Add a kill switch flag for payments',
    ],
  },
];

export function getSample(id: string): Sample | undefined {
  return SAMPLES.find((s) => s.id === id);
}
