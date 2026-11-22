import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'package-json-guide',
    title: 'package.json Explained: Fields, exports, scripts and Examples',
    description:
      'A field-by-field guide to package.json: name and version, "type": "module", the exports map, scripts, engines, and the dependency groups. Includes a copy-ready modern example.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['package.json', 'npm', 'node', 'javascript', 'esm'],
    readingTime: '7 min',
    aiSummary:
      'package.json is the manifest every JavaScript package manager reads. name and version are required to publish. "type": "module" makes .js files ESM. The exports map defines the public entry points, with "types" first. scripts run with npm run. engines declares the Node range. dependencies, devDependencies and peerDependencies separate runtime, build-time and host-provided packages. Use files to publish only build output, and private: true on apps.',
    relatedTemplates: ['package-json', 'tsconfig-json'],
    relatedBlogs: ['tsconfig-json-guide', 'devcontainer-json-guide'],
    faq: [
      {
        q: 'What is the difference between dependencies and devDependencies?',
        a: 'dependencies are installed wherever your package is installed and are needed at runtime. devDependencies are only installed for local development and CI: compilers, test runners, linters. peerDependencies are packages the host app must provide, like react for a component library.',
      },
      {
        q: 'Do I still need "main" if I have "exports"?',
        a: 'Modern Node and bundlers use "exports" and ignore "main" when both exist. Keep "main" only if you must support very old tooling. Note that "exports" is strict: any path you do not list cannot be imported.',
      },
      {
        q: 'What do ^ and ~ mean in versions?',
        a: '^1.4.0 accepts any 1.x.y at or above 1.4.0 (no new major). ~1.4.0 accepts only 1.4.x patches. An exact "1.4.0" pins one version. The lockfile records what was actually installed.',
      },
      {
        q: 'Is a comment allowed in package.json?',
        a: 'No. package.json is strict JSON, so comments and trailing commas break npm. Use a "//" key if you must leave a note, or document it in the README.',
      },
    ],
  },
  body: `\`package.json\` is the one file every JavaScript project has. npm, pnpm, Yarn and Bun all read it, and most of its fields come down to a few decisions.

## Identity: name and version

\`\`\`json
{ "name": "@acme/widgets", "version": "1.4.0", "license": "MIT" }
\`\`\`

- **name**: lowercase and URL-safe, optionally scoped (\`@org/name\`). Required to publish.
- **version**: semver. Bump the major for breaking changes, the minor for features and the patch for fixes.

For an app you never publish, add \`"private": true\` so \`npm publish\` refuses to run.

## Module system: "type"

\`"type": "module"\` makes every \`.js\` file an ES module (\`import\` / \`export\`). Without it, \`.js\` files are CommonJS (\`require\`). Either way, \`.mjs\` is always ESM and \`.cjs\` is always CommonJS.

## Entry points: the exports map

\`exports\` is the modern replacement for \`main\`. It lists exactly what consumers can import:

\`\`\`json
"exports": {
  ".": {
    "types": "./dist/index.d.ts",
    "import": "./dist/index.js",
    "require": "./dist/index.cjs"
  },
  "./package.json": "./package.json"
}
\`\`\`

- Put \`types\` **first**. Conditions are matched in order.
- Anything not listed is private. Consumers can no longer deep-import \`dist/internal.js\`.
- Ship only an \`import\` condition if you only publish ESM.

## scripts

\`\`\`json
"scripts": {
  "build": "tsc -p tsconfig.build.json",
  "test": "vitest run",
  "lint": "eslint .",
  "prepublishOnly": "npm run build"
}
\`\`\`

Run them with \`npm run build\`. \`test\` and \`start\` also work without \`run\`. Lifecycle names such as \`prepublishOnly\` or \`postinstall\` run automatically.

## engines

\`"engines": { "node": ">=22" }\` documents the supported runtime. Node 20 reached end-of-life in April 2026, so new projects should target 22 or 24. npm only warns on a mismatch unless you set \`engine-strict\`.

## The three dependency groups

| Field | Installed when | Example |
|---|---|---|
| \`dependencies\` | always, at runtime | \`zod\` |
| \`devDependencies\` | local dev and CI only | \`typescript\`, \`vitest\` |
| \`peerDependencies\` | the host app provides it | \`react\` in a component library |

## Publish only what you mean to

\`"files": ["dist"]\` is an allow-list for \`npm publish\`. Without it you can ship tests, fixtures, or worse, a stray \`.env\`. Check what will be published with \`npm pack --dry-run\`.

## Security notes

- \`postinstall\` scripts in your dependencies run on every machine that installs them. Review new packages, and consider \`--ignore-scripts\` in CI.
- Commit the lockfile so CI installs exactly what you tested.
- Run \`npm audit\` or a registry scanner on every pull request.

Open the package.json template and ask the workspace to "add a CommonJS entry to the exports map" or "move typescript to devDependencies", then review the diff.`,
};
