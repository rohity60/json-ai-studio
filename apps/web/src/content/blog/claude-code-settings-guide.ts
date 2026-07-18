import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'claude-code-settings-guide',
    title: 'Configuring Claude Code with settings.json',
    description:
      'How .claude/settings.json shapes the agent — permission allow/deny/ask rules, lifecycle hooks, environment variables and model overrides — and why deny always wins.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['claude-code', 'ai', 'agent', 'permissions'],
    readingTime: '6 min',
    aiSummary:
      '.claude/settings.json governs Claude Code in a repo. permissions has allow/deny/ask arrays of tool-pattern rules, and deny always wins. hooks run shell commands on events like PostToolUse. env injects variables; model overrides the model. Allow only narrow safe patterns, deny secret paths, and use ask for irreversible actions like git push.',
    relatedTemplates: ['claude-code-settings'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Where do settings files live and which wins?',
        a: 'Project settings are in .claude/settings.json (shared) and .claude/settings.local.json (personal, git-ignored); user settings are in ~/.claude/settings.json. More specific scopes and deny rules take precedence.',
      },
      {
        q: 'What can a hook do?',
        a: 'A hook runs a shell command on an event — e.g. PostToolUse after an edit to auto-format, or Stop when the agent finishes. Hooks run with your shell privileges, so review them.',
      },
    ],
  },
  body: `\`.claude/settings.json\` decides how Claude Code behaves in a project — what runs without asking, what is always blocked, and what happens automatically around each action.

## permissions: allow, deny, ask

Three arrays of tool-pattern rules:

\`\`\`json
"permissions": {
  "allow": ["Bash(npm run test:*)", "Read(./src/**)"],
  "ask":   ["Bash(git push:*)"],
  "deny":  ["Read(./.env)", "Bash(rm -rf:*)"]
}
\`\`\`

- **allow** — run without prompting. Keep patterns narrow.
- **ask** — prompt every time. Right for irreversible actions.
- **deny** — never allowed. **deny always wins** over allow.

Put secret paths and destructive commands in \`deny\` and you have a hard floor no allow rule can override.

## hooks: run commands on events

Hooks fire shell commands on lifecycle events. A \`PostToolUse\` hook that formats after every edit:

\`\`\`json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Edit|Write",
      "hooks": [ { "type": "command", "command": "npx prettier --write \\"$CLAUDE_FILE_PATHS\\"" } ]
    }
  ]
}
\`\`\`

## env and model

\`env\` injects environment variables into the session; \`model\` overrides which model this project uses. Both are optional — an empty \`{}\` is a valid settings file.

## Where it lives

Shared project rules go in \`.claude/settings.json\`; personal overrides in \`.claude/settings.local.json\` (git-ignored); global defaults in \`~/.claude/settings.json\`.

## Security notes

- \`deny\` beats \`allow\` — lean on it for secrets and destructive commands.
- Do not store API keys here; reference them via \`env\` or a separate secrets file.
- Hook commands run automatically with your privileges — read them before trusting a shared config.

Open the Claude Code settings template and ask the workspace to "deny access to the .env file" or "add a hook that runs prettier after edits", then diff the result.`,
};
