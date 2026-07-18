import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'devcontainer-json-guide',
    title: 'The devcontainer.json Guide',
    description:
      'What each block of a devcontainer.json does — image vs build, features, forwardPorts, customizations and postCreateCommand — and how the same file powers both GitHub Codespaces and local VS Code Dev Containers.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['devcontainer', 'codespaces', 'vscode', 'docker'],
    readingTime: '5 min',
    aiSummary:
      'devcontainer.json describes a reproducible dev environment. image (or build) picks the base; features add reusable toolchains like docker-in-docker or a language runtime; forwardPorts surfaces container ports; customizations.vscode pre-installs extensions and settings; postCreateCommand runs once after creation. The same file works in Codespaces and local VS Code. Pin versions and run as a non-root remoteUser.',
    relatedTemplates: ['devcontainer-json'],
    relatedBlogs: [],
    faq: [
      {
        q: 'image or build — which do I use?',
        a: 'Use image to pull a prebuilt base (fastest, most common). Use build with a Dockerfile only when you need to bake in steps that features cannot express. You set one or the other, not both.',
      },
      {
        q: 'Does the same file work in Codespaces and locally?',
        a: 'Yes. GitHub Codespaces and the VS Code Dev Containers extension read the same devcontainer.json, so one file gives every contributor and every cloud environment the same setup.',
      },
    ],
  },
  body: `A \`devcontainer.json\` tells your IDE — GitHub Codespaces or local VS Code — how to build the environment your code runs in: which image, which tools, which ports, which extensions. One file, and every contributor gets the same setup.

## image vs build

The base can be a prebuilt image (fastest, most common):

\`\`\`json
{ "image": "mcr.microsoft.com/devcontainers/javascript-node:20-bookworm" }
\`\`\`

or a \`build\` pointing at a Dockerfile when you need custom bake-in steps. Set one, not both.

## features: reusable toolchains

\`features\` are versioned add-ons you compose in without writing Dockerfile lines — a language runtime, the GitHub CLI, or Docker itself:

\`\`\`json
"features": {
  "ghcr.io/devcontainers/features/docker-in-docker:2": { "moby": true }
}
\`\`\`

Want a different stack? Swap the base image and one feature — that is the difference between the "Python", "Go" and "Node" configs people search for.

## forwardPorts

List the container ports you want on your machine. \`portsAttributes\` labels them and controls auto-forward behavior:

\`\`\`json
"forwardPorts": [3000, 5432]
\`\`\`

## customizations.vscode

Pre-install extensions and apply settings the moment the container launches:

\`\`\`json
"customizations": {
  "vscode": {
    "extensions": ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"],
    "settings": { "editor.formatOnSave": true }
  }
}
\`\`\`

## postCreateCommand

Runs **once** after the container is created — the right place for \`npm install\` or \`pip install -r requirements.txt\`. Keeping install steps here (not in the image) keeps the image cacheable.

## Security notes

- Never bake secrets into the image or this file — use Codespaces secrets or an env file.
- \`docker-in-docker\` is privileged; add it only when the workflow needs it.
- Run as a non-root \`remoteUser\` such as \`node\` or \`vscode\`.

Open the Dev Container template and ask the workspace to "switch this to a Python 3.12 base image" or "forward port 5432 for Postgres", then diff the result.`,
};
