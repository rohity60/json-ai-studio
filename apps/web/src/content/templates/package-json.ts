import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'package-json',
    slug: 'package-json',
    title: 'package.json (Node.js / npm)',
    description:
      'A modern package.json for a Node.js app or library: ESM "type", an "exports" map, engines, scripts, and dependency groups. It is the manifest npm, pnpm, Yarn and Bun all read.',
    category: 'JavaScript',
    provider: 'npm',
    difficulty: 'beginner',
    estimatedReadTime: '6 min',
    tags: ['package.json', 'npm', 'node', 'javascript', 'esm', 'exports'],
    schemaVersion: 'npm 11',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a "test" script that runs vitest',
      'Add a CommonJS entry to the exports map',
      'Move typescript to devDependencies',
      'Pin the Node engine to version 22 or newer',
    ],
    relatedTemplates: ['tsconfig-json', 'github-actions-workflow', 'devcontainer-json'],
    relatedBlogs: ['package-json-guide', 'tsconfig-json-guide'],
    purpose:
      'Describe a JavaScript package: its name and version, how it is imported, which scripts it runs, and what it depends on.',
    whenToUse:
      'Every Node.js project, whether an app, a library or a monorepo workspace. Edit it to add scripts, change entry points or manage dependencies.',
    requiredFields: [
      'name: lowercase, URL-safe, optionally scoped (@org/name); required to publish',
      'version: a semver string such as "1.2.0"; required to publish',
    ],
    optionalFields: [
      'type: "module" makes .js files ESM; omit it (or use "commonjs") for CommonJS',
      'exports: the public entry points; anything not listed cannot be imported',
      'scripts: commands run with npm run <name>',
      'engines: the supported Node.js range',
      'dependencies / devDependencies / peerDependencies: runtime, build-time and host-provided packages',
      'files: allow-list of what gets published',
      'private: true blocks accidental npm publish',
    ],
    bestPractices: [
      'Use an "exports" map instead of "main" alone; it also hides internal files.',
      'Put the "types" condition first inside each exports entry.',
      'Keep build tools (typescript, vitest, eslint) in devDependencies.',
      'Commit the lockfile, and set "private": true on apps that are never published.',
    ],
    security: [
      'Review new dependencies and their install scripts; postinstall runs code on every machine.',
      'Use "files" to publish only build output, never .env files or tests.',
      'Run npm audit (or your registry scanner) in CI.',
    ],
    formatSignature: ['/name', '/version', '/scripts'],
  },
  json: {
    name: '@acme/widgets',
    version: '1.4.0',
    description: 'Reusable widget components',
    license: 'MIT',
    type: 'module',
    exports: {
      '.': {
        types: './dist/index.d.ts',
        import: './dist/index.js',
      },
      './package.json': './package.json',
    },
    files: ['dist'],
    engines: { node: '>=22' },
    scripts: {
      build: 'tsc -p tsconfig.build.json',
      dev: 'tsc -w',
      test: 'vitest run',
      lint: 'eslint .',
      prepublishOnly: 'npm run build',
    },
    dependencies: {
      zod: '^4.1.0',
    },
    devDependencies: {
      typescript: '^5.9.0',
      vitest: '^4.0.0',
      eslint: '^9.30.0',
    },
    peerDependencies: {
      react: '>=18',
    },
  },
};
