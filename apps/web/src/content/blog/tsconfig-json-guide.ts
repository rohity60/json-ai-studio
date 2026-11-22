import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'tsconfig-json-guide',
    title: 'tsconfig.json Explained: The Options That Matter',
    description:
      'A practical tsconfig.json guide: target, module and moduleResolution (nodenext vs bundler), strict mode and its useful extras, paths aliases, declaration output and project references.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['tsconfig', 'typescript', 'compiler', 'esm'],
    readingTime: '7 min',
    aiSummary:
      'tsconfig.json controls the TypeScript compiler. Pick module/moduleResolution by runtime: "nodenext" for code Node runs directly, "esnext" + "bundler" for Vite or webpack apps. Turn on strict, plus noUncheckedIndexedAccess and verbatimModuleSyntax. target sets the emitted JS level (ES2022+ is safe for current Node and browsers). paths aliases must also be configured in the runtime or bundler. Use extends for shared bases and references + composite for monorepos.',
    relatedTemplates: ['tsconfig-json', 'package-json'],
    relatedBlogs: ['package-json-guide', 'vscode-tasks-json-guide'],
    faq: [
      {
        q: 'nodenext or bundler for moduleResolution?',
        a: 'Use "nodenext" (with "module": "nodenext") when Node runs the compiled output directly; it enforces Node\'s real rules, such as file extensions in relative ESM imports. Use "bundler" (with "module": "esnext") when Vite, webpack, esbuild or Bun resolves imports for you.',
      },
      {
        q: 'Why do my paths aliases fail at runtime?',
        a: 'paths only tells the type checker where imports resolve. tsc does not rewrite them in the output, so Node or your bundler must know the alias too, for example through package.json "imports" (#lib/*) or a Vite resolve.alias.',
      },
      {
        q: 'Does tsconfig.json allow comments?',
        a: 'Yes. tsconfig.json is parsed as JSONC, so comments and trailing commas are accepted, unlike package.json.',
      },
    ],
  },
  body: `\`tsconfig.json\` has well over a hundred options, but a good config is mostly a few decisions. Get these right and the rest can stay on defaults.

## 1. How imports resolve: module + moduleResolution

This is the setting people get wrong most often. Pick by **who runs the output**:

| Runtime | module | moduleResolution |
|---|---|---|
| Node runs the compiled JS | \`nodenext\` | \`nodenext\` |
| Vite / webpack / esbuild / Bun bundles it | \`esnext\` | \`bundler\` |

With \`nodenext\`, TypeScript follows Node's real rules. That means relative ESM imports need extensions (\`./util.js\`), and \`"type"\` in package.json decides ESM vs CommonJS.

## 2. What JavaScript to emit: target and lib

\`target\` sets the syntax level of the output. \`ES2022\` or newer is safe for current Node LTS versions and evergreen browsers. \`lib\` sets which built-in APIs the type checker knows about. Add \`"DOM"\` for browser code.

## 3. How strict: strict plus a few extras

\`\`\`json
"strict": true,
"noUncheckedIndexedAccess": true,
"noImplicitOverride": true,
"verbatimModuleSyntax": true
\`\`\`

- **strict** turns on the core family (\`strictNullChecks\`, \`noImplicitAny\`, …). Enable it on day one.
- **noUncheckedIndexedAccess** types \`arr[i]\` as \`T | undefined\`, which catches real bugs.
- **verbatimModuleSyntax** makes you write \`import type\` for type-only imports, so emitted imports are predictable.

## 4. Output: outDir, declaration, sourceMap

For a library, set \`"declaration": true\` so consumers get \`.d.ts\` files, and point package.json \`exports.types\` at them. \`rootDir\` + \`outDir\` keep the \`src/\` → \`dist/\` layout tidy.

## 5. Aliases: paths

\`\`\`json
"paths": { "#lib/*": ["./src/lib/*"] }
\`\`\`

Remember \`paths\` only affects type checking. Mirror it in package.json \`"imports"\` (which is why the \`#\` prefix works well) or in your bundler config.

## 6. Sharing and monorepos: extends and references

- \`"extends": "@tsconfig/node22/tsconfig.json"\` inherits a maintained base.
- In a monorepo, each package sets \`"composite": true\`, and a root tsconfig lists them in \`references\`. Build with \`tsc -b\`.

## Security and correctness notes

- \`skipLibCheck: true\` speeds builds but hides type errors inside dependencies.
- A clean type check is not runtime validation. Validate untrusted JSON with a schema (see the JSON Schema guide).

Open the tsconfig template and ask the workspace to "switch this to a bundler setup for Vite" or "add a path alias", then diff the result.`,
};
