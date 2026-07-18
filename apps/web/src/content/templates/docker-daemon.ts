import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'docker-daemon',
    slug: 'docker-daemon',
    title: 'Docker daemon.json (Production)',
    description:
      'A production-minded Docker daemon.json with log rotation, the overlay2 storage driver, live-restore and sane concurrency limits.',
    category: 'DevOps',
    provider: 'Docker',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['docker', 'devops', 'daemon', 'logging', 'containers'],
    schemaVersion: '1.0',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Set the default address pool',
      'Add a private registry mirror',
      'Cap container logs at 5 files of 20MB',
      'Enable metrics on localhost only',
    ],
    relatedTemplates: [],
    relatedBlogs: ['docker-daemon-json-guide'],
    purpose:
      'Configure the Docker Engine host-wide: logging, storage driver, restart behaviour and resource limits.',
    whenToUse:
      'On a server or CI host running the Docker daemon, placed at /etc/docker/daemon.json and applied with a daemon restart.',
    requiredFields: [
      'No fields are required — daemon.json overrides engine defaults selectively.',
    ],
    optionalFields: [
      'log-driver / log-opts — logging backend and rotation',
      'storage-driver — e.g. overlay2',
      'live-restore — keep containers running while the daemon restarts',
      'default-ulimits, max-concurrent-downloads — resource tuning',
    ],
    bestPractices: [
      'Always set log rotation (max-size/max-file) or disks fill silently.',
      'Enable live-restore to survive daemon upgrades without downtime.',
      'Validate with `dockerd --validate` before restarting in production.',
    ],
    security: [
      'Never expose the daemon on tcp:// without TLS — it is root-equivalent.',
      'Bind metrics/experimental endpoints to 127.0.0.1 only.',
    ],
  },
  json: {
    'log-driver': 'json-file',
    'log-opts': { 'max-size': '10m', 'max-file': '3' },
    'storage-driver': 'overlay2',
    'live-restore': true,
    'max-concurrent-downloads': 3,
    'max-concurrent-uploads': 5,
    'default-ulimits': {
      nofile: { Name: 'nofile', Hard: 64000, Soft: 64000 },
    },
    'metrics-addr': '127.0.0.1:9323',
    experimental: false,
  },
};
