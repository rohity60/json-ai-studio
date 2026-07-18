import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'vscode-launch-json',
    slug: 'vscode-launch-json',
    title: 'VS Code launch.json (Debug Config)',
    description:
      'A .vscode/launch.json with debug configurations — launch a Node program, attach to a running process, and a compound that starts several at once — the file behind the VS Code Run and Debug panel.',
    category: 'IDE',
    provider: 'VS Code',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['vscode', 'debug', 'launch', 'node', 'ide'],
    schemaVersion: '0.2.0',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a configuration to debug Jest tests',
      'Add a Chrome launch config for the frontend',
      'Set an environment variable on the launch config',
      'Add a preLaunchTask that builds first',
    ],
    relatedTemplates: ['vscode-tasks-json', 'vscode-settings'],
    relatedBlogs: ['vscode-launch-json-guide'],
    purpose:
      'Define how VS Code starts or attaches a debugger — the configurations that populate the Run and Debug dropdown.',
    whenToUse:
      'Debugging an app in VS Code: launching your server with breakpoints, attaching to a Node process, or debugging tests and the browser together.',
    requiredFields: [
      'version — the launch schema version, "0.2.0"',
      'configurations — the array of debug configurations',
      'type / request / name — per configuration',
    ],
    optionalFields: [
      'program — the entry file for a launch configuration',
      'env — environment variables for the debugee',
      'preLaunchTask — a tasks.json task to run before launching',
      'compounds — start multiple configurations together',
    ],
    bestPractices: [
      'Use ${workspaceFolder} and ${file} variables instead of absolute paths.',
      'Wire a preLaunchTask to build before launching compiled languages.',
      'Group frontend + backend into a compound for full-stack debugging.',
    ],
    security: [
      'Do not hardcode secrets in env; use an envFile pointing at a git-ignored .env.',
      'Avoid committing configs that attach to production ports or hosts.',
      'Keep launch.json in .vscode and out of any published package.',
    ],
  },
  json: {
    version: '0.2.0',
    configurations: [
      {
        type: 'node',
        request: 'launch',
        name: 'Launch Server',
        program: '${workspaceFolder}/src/index.js',
        env: { NODE_ENV: 'development' },
        preLaunchTask: 'build',
        skipFiles: ['<node_internals>/**'],
      },
      {
        type: 'node',
        request: 'attach',
        name: 'Attach to Process',
        port: 9229,
      },
    ],
    compounds: [
      {
        name: 'Full Stack',
        configurations: ['Launch Server', 'Attach to Process'],
      },
    ],
  },
};
