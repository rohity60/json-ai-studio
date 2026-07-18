import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'vscode-tasks-json-guide',
    title: 'The VS Code tasks.json Guide',
    description:
      'How tasks.json turns shell commands into first-class VS Code actions — the default build task, background watch tasks with problem matchers, and chaining with dependsOn.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['vscode', 'tasks', 'build', 'ide'],
    readingTime: '5 min',
    aiSummary:
      'tasks.json (version 2.0.0) defines a tasks array VS Code can run from the Command Palette. group marks the default build/test task; problemMatcher parses output into the Problems panel; isBackground keeps watch tasks running; dependsOn chains tasks. Give exactly one default build task, attach a matcher to watches, and compose with dependsOn instead of shell &&.',
    relatedTemplates: ['vscode-tasks-json'],
    relatedBlogs: [],
    faq: [
      {
        q: 'What does problemMatcher do?',
        a: 'It parses task output and turns errors/warnings into entries in the Problems panel with clickable file locations. Built-ins like $tsc and $eslint-stylish cover common tools.',
      },
      {
        q: 'How do I run one task before another?',
        a: 'Use dependsOn with the labels of the tasks to run first. It is cleaner and more portable than chaining commands with && in a single shell task.',
      },
    ],
  },
  body: `\`tasks.json\` turns your build and test commands into VS Code actions you can trigger from the Command Palette or wire into the debugger.

## A default build task

Mark one task as the default build so Ctrl/Cmd+Shift+B just runs it:

\`\`\`json
{
  "label": "build",
  "type": "shell",
  "command": "npm run build",
  "group": { "kind": "build", "isDefault": true },
  "problemMatcher": ["$tsc"]
}
\`\`\`

The \`problemMatcher\` parses compiler output into the Problems panel.

## Background watch tasks

Long-running watchers set \`isBackground\` and a watch matcher so errors surface as you type:

\`\`\`json
{ "label": "watch", "type": "shell", "command": "npm run watch", "isBackground": true, "problemMatcher": ["$tsc-watch"] }
\`\`\`

## Chain tasks with dependsOn

Compose tasks instead of stringing shell commands with \`&&\`:

\`\`\`json
{ "label": "test", "type": "shell", "command": "npm test", "group": "test", "dependsOn": ["build"] }
\`\`\`

Now running \`test\` builds first.

## Ties into launch.json

A task label here is exactly what \`preLaunchTask\` in \`launch.json\` points at — so your debugger always builds before it runs.

## Security notes

- Keep secrets out of \`command\` and \`args\`; read them from the environment.
- Be careful with tasks that auto-run on folder open (\`runOptions.runOn\`).
- Review any task that pipes untrusted input into a shell.

Open the tasks.json template and ask the workspace to "add a task that runs the linter" or "chain build then test with dependsOn", then diff the result.`,
};
