import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'devcontainer-json',
    slug: 'devcontainer-json',
    title: 'Dev Container (devcontainer.json)',
    description:
      'A devcontainer.json that defines a reproducible Node.js dev environment for GitHub Codespaces and VS Code — base image, dev container features, forwarded ports, pre-installed extensions and a post-create setup step.',
    category: 'IDE',
    provider: 'Dev Containers',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['devcontainer', 'codespaces', 'vscode', 'docker', 'environment'],
    schemaVersion: 'devcontainer-v1',
    featured: true,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Switch this to a Python 3.12 base image',
      'Add the Docker-in-Docker feature',
      'Forward port 5432 for Postgres',
      'Add the Go toolchain feature',
    ],
    relatedTemplates: ['vscode-settings', 'docker-daemon'],
    relatedBlogs: ['devcontainer-json-guide'],
    purpose:
      'Describe a reproducible, containerized development environment so every contributor (and every Codespace) gets the same tools, ports and editor setup.',
    whenToUse:
      'Onboarding a repo to GitHub Codespaces or VS Code Dev Containers, or standardizing "works on my machine" toolchains across a team.',
    requiredFields: [
      'image OR build — the base container image, or a Dockerfile to build',
    ],
    optionalFields: [
      'features — reusable add-ons (docker-in-docker, language toolchains)',
      'forwardPorts — container ports surfaced to your machine',
      'customizations.vscode — extensions and settings applied on launch',
      'postCreateCommand — a command run once after the container is created',
      'remoteUser — the non-root user the IDE runs as',
    ],
    bestPractices: [
      'Pin the base image and each feature to a version; do not float on latest.',
      'Install dependencies in postCreateCommand so the image stays cacheable.',
      'Run as a non-root remoteUser (e.g. node, vscode) rather than root.',
    ],
    security: [
      'Do not bake secrets into the image or devcontainer.json; use Codespaces secrets or env files.',
      'docker-in-docker grants broad privileges — add it only when the workflow needs it.',
      'Prefer official/verified feature sources over arbitrary third-party ones.',
    ],
  },
  json: {
    name: 'Node.js Dev Container',
    image: 'mcr.microsoft.com/devcontainers/javascript-node:20-bookworm',
    features: {
      'ghcr.io/devcontainers/features/github-cli:1': {},
      'ghcr.io/devcontainers/features/docker-in-docker:2': {
        version: 'latest',
        moby: true,
      },
    },
    forwardPorts: [3000, 5432],
    portsAttributes: {
      '3000': { label: 'app', onAutoForward: 'notify' },
      '5432': { label: 'postgres', onAutoForward: 'silent' },
    },
    customizations: {
      vscode: {
        extensions: [
          'dbaeumer.vscode-eslint',
          'esbenp.prettier-vscode',
          'ms-azuretools.vscode-docker',
        ],
        settings: {
          'editor.formatOnSave': true,
          'editor.defaultFormatter': 'esbenp.prettier-vscode',
        },
      },
    },
    postCreateCommand: 'npm install',
    remoteUser: 'node',
  },
};
