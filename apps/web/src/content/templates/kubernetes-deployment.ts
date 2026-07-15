import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'kubernetes-deployment',
    slug: 'kubernetes-deployment',
    title: 'Kubernetes Deployment (JSON)',
    description:
      'A Kubernetes Deployment manifest in JSON with replicas, a rolling-update strategy, resource limits, probes and a security context — production defaults.',
    category: 'DevOps',
    provider: 'Kubernetes',
    difficulty: 'advanced',
    estimatedReadTime: '7 min',
    tags: ['kubernetes', 'k8s', 'deployment', 'devops', 'containers'],
    schemaVersion: 'apps/v1',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain each part of this Deployment',
      'Scale this to 5 replicas',
      'Add a liveness probe on /healthz',
      'Add an environment variable from a secret',
    ],
    relatedTemplates: ['docker-daemon', 'github-actions-workflow'],
    relatedBlogs: [],
    purpose:
      'Declare a self-healing, horizontally-scalable workload with health checks and resource bounds.',
    whenToUse:
      'Deploying a stateless service to a Kubernetes cluster via kubectl apply or a GitOps pipeline.',
    requiredFields: [
      'apiVersion — apps/v1 for Deployments',
      'kind — "Deployment"',
      'metadata.name — the Deployment name',
      'spec.selector + spec.template — pod selection and template',
    ],
    optionalFields: [
      'spec.replicas — desired pod count',
      'spec.strategy — rolling update parameters',
      'resources.requests/limits — scheduling and cgroup bounds',
      'livenessProbe / readinessProbe — health checks',
    ],
    bestPractices: [
      'Always set resource requests and limits so the scheduler can bin-pack.',
      'Define both liveness and readiness probes.',
      'Run as non-root with a restrictive securityContext.',
    ],
    security: [
      'Set runAsNonRoot and drop all capabilities unless required.',
      'Never bake secrets into the image; mount them from Secrets.',
      'Pin image tags by digest in production, not :latest.',
    ],
  },
  json: {
    apiVersion: 'apps/v1',
    kind: 'Deployment',
    metadata: { name: 'web', labels: { app: 'web' } },
    spec: {
      replicas: 3,
      selector: { matchLabels: { app: 'web' } },
      strategy: {
        type: 'RollingUpdate',
        rollingUpdate: { maxSurge: 1, maxUnavailable: 0 },
      },
      template: {
        metadata: { labels: { app: 'web' } },
        spec: {
          securityContext: { runAsNonRoot: true, runAsUser: 1000 },
          containers: [
            {
              name: 'web',
              image: 'ghcr.io/example/web:1.4.2',
              ports: [{ containerPort: 8080 }],
              resources: {
                requests: { cpu: '100m', memory: '128Mi' },
                limits: { cpu: '500m', memory: '256Mi' },
              },
              readinessProbe: {
                httpGet: { path: '/ready', port: 8080 },
                initialDelaySeconds: 5,
              },
              livenessProbe: {
                httpGet: { path: '/healthz', port: 8080 },
                initialDelaySeconds: 10,
              },
            },
          ],
        },
      },
    },
  },
};
