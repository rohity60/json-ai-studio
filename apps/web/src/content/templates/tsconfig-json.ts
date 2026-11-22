import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'tsconfig-json',
    slug: 'tsconfig-json',
    title: 'tsconfig.json (TypeScript)',
    description:
      'A strict, modern tsconfig.json for a Node.js or bundler project: target, module and moduleResolution, strict mode, declaration output and path aliases. It controls how tsc type-checks and emits.',
    category: 'JavaScript',
    provider: 'TypeScript',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['tsconfig', 'typescript', 'compiler', 'node', 'esm'],
    schemaVersion: 'TypeScript 5.x',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Switch this to a bundler setup for Vite',
      'Add a path alias @/* pointing at src/*',
      'Turn on noUncheckedIndexedAccess',
      'Make this a project reference for a monorepo',
    ],
    relatedTemplates: ['package-json', 'vscode-settings'],
    relatedBlogs: ['tsconfig-json-guide', 'package-json-guide'],
    purpose:
      'Tell the TypeScript compiler which files make up the project, how strictly to type-check them and what JavaScript to emit.',
    whenToUse:
      'Any TypeScript project. Start from this when you create a project, or use it to compare against a config you inherited.',
    requiredFields: [
      'compilerOptions: the compiler settings (an empty tsconfig still works on defaults, but you rarely want them)',
    ],
    optionalFields: [
      'include / exclude / files: which sources are in the project',
      'extends: inherit from a shared base such as @tsconfig/node22',
      'references: project references for monorepos (with composite: true)',
      'compilerOptions.paths: import aliases',
    ],
    bestPractices: [
      'Turn on "strict": true from day one; retrofitting it later is painful.',
      'For Node, pair "module": "nodenext" with "moduleResolution": "nodenext"; for Vite/webpack apps use "module": "esnext" with "moduleResolution": "bundler".',
      'Add "noUncheckedIndexedAccess" to catch undefined array and record lookups.',
      'Use "verbatimModuleSyntax" so type-only imports are explicit and erased predictably.',
    ],
    security: [
      'tsconfig has no secrets, but "paths" aliases must also be configured in your runtime or bundler, or imports break in production.',
      'Keep "skipLibCheck" on only as a speed trade-off; it hides type errors in dependencies.',
    ],
    formatSignature: ['/compilerOptions'],
  },
  json: {
    $schema: 'https://json.schemastore.org/tsconfig',
    compilerOptions: {
      target: 'ES2023',
      module: 'nodenext',
      moduleResolution: 'nodenext',
      lib: ['ES2023'],
      strict: true,
      noUncheckedIndexedAccess: true,
      noImplicitOverride: true,
      verbatimModuleSyntax: true,
      isolatedModules: true,
      esModuleInterop: true,
      resolveJsonModule: true,
      skipLibCheck: true,
      declaration: true,
      sourceMap: true,
      outDir: 'dist',
      rootDir: 'src',
      paths: { '#lib/*': ['./src/lib/*'] },
    },
    include: ['src'],
    exclude: ['node_modules', 'dist'],
  },
};
