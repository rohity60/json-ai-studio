import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'vscode-launch-json-guide',
    title: 'The VS Code launch.json Guide',
    description:
      'How launch.json drives the VS Code debugger — launch vs attach requests, useful variables like ${workspaceFolder}, preLaunchTask wiring, and compounds for full-stack debugging.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['vscode', 'debug', 'launch', 'ide'],
    readingTime: '5 min',
    aiSummary:
      'launch.json (version 0.2.0) holds a configurations array that populates the Run and Debug dropdown. request:"launch" starts a program; request:"attach" connects to a running process. Use ${workspaceFolder} variables, wire preLaunchTask to a tasks.json task to build first, and use compounds to start frontend and backend together.',
    relatedTemplates: ['vscode-launch-json'],
    relatedBlogs: [],
    faq: [
      {
        q: 'launch vs attach?',
        a: 'request:"launch" starts your program under the debugger. request:"attach" connects to a process that is already running (e.g. node --inspect on port 9229). Use attach for servers you start yourself.',
      },
      {
        q: 'How do I build before debugging?',
        a: 'Set preLaunchTask to the label of a tasks.json task. VS Code runs that task and only launches once it succeeds — essential for compiled languages.',
      },
    ],
  },
  body: `\`launch.json\` lives in \`.vscode\` and defines every entry in the Run and Debug dropdown. Two request types cover most cases.

## launch: start a program

\`\`\`json
{
  "type": "node",
  "request": "launch",
  "name": "Launch Server",
  "program": "\${workspaceFolder}/src/index.js",
  "env": { "NODE_ENV": "development" }
}
\`\`\`

Use variables like \`\${workspaceFolder}\` and \`\${file}\` instead of absolute paths so the config is portable.

## attach: connect to a running process

\`\`\`json
{ "type": "node", "request": "attach", "name": "Attach to Process", "port": 9229 }
\`\`\`

Great for a server you already started with \`--inspect\`.

## Build first with preLaunchTask

Point \`preLaunchTask\` at a \`tasks.json\` label and VS Code builds before it launches:

\`\`\`json
"preLaunchTask": "build"
\`\`\`

## Debug the whole stack with compounds

\`compounds\` starts several configurations at once — frontend and backend under one click:

\`\`\`json
"compounds": [
  { "name": "Full Stack", "configurations": ["Launch Server", "Attach to Process"] }
]
\`\`\`

## Security notes

- Do not hardcode secrets in \`env\`; use \`envFile\` pointing at a git-ignored \`.env\`.
- Avoid committing configs that attach to production hosts or ports.

Open the launch.json template and ask the workspace to "add a configuration to debug Jest tests" or "add a Chrome launch config for the frontend", then diff the result.`,
};
