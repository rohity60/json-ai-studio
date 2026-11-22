import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'claude-code-settings-guide',
    title: 'Configuring Claude Code with settings.json',
    description:
      'How .claude/settings.json shapes the agent — permission allow/deny/ask rules, lifecycle hooks, environment variables and model overrides — and why deny always wins.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['claude-code', 'ai', 'agent', 'permissions'],
    readingTime: '6 min',
    aiSummary:
      '.claude/settings.json governs Claude Code in a repo. permissions has allow/deny/ask arrays of tool-pattern rules, and deny always wins. hooks run shell commands on events like PostToolUse. env injects variables; model overrides the model. Allow only narrow safe patterns, deny secret paths, and use ask for irreversible actions like git push.',
    relatedTemplates: ['claude-code-settings'],
    relatedBlogs: ['mcp-json-guide', 'vscode-tasks-json-guide'],
    faq: [
      {
        q: 'Where do settings files live and which wins?',
        a: 'User settings live in ~/.claude/settings.json, shared project settings in .claude/settings.json, and personal project overrides in .claude/settings.local.json (git-ignored). For ordinary keys the more specific scope wins (managed policy > command-line flags > local > project > user). Permission rules from every scope are combined, and a deny anywhere beats an allow.',
      },
      {
        q: 'What can a hook do?',
        a: 'A hook runs a shell command on an event — e.g. PostToolUse after an edit to auto-format, or Stop when the agent finishes. The event arrives as JSON on stdin (the edited path is at .tool_input.file_path). A PreToolUse hook can also block a call by exiting with code 2. Hooks run with your shell privileges, so review them.',
      },
      {
        q: 'Why does my hook get an empty file path?',
        a: 'Older examples read an environment variable such as $CLAUDE_FILE_PATHS. Claude Code does not set it: hooks receive their input as JSON on stdin. Parse it, for example with jq -r \'.tool_input.file_path\'.',
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
      "hooks": [ { "type": "command", "command": "jq -r '.tool_input.file_path' | xargs npx prettier --write" } ]
    }
  ]
}
\`\`\`

Hooks get the event as **JSON on stdin**, not as environment variables. For an edit, the path is at \`tool_input.file_path\`. That is why the command pipes stdin through \`jq\`. Older snippets that read \`$CLAUDE_FILE_PATHS\` silently receive an empty string.

Useful events:

| Event | Fires | Typical use |
|---|---|---|
| \`PreToolUse\` | before a tool runs | block a command (exit code 2) |
| \`PostToolUse\` | after a tool succeeds | format, lint, run tests |
| \`UserPromptSubmit\` | when you send a prompt | inject context |
| \`Stop\` | when the agent finishes | notify, final checks |

## env and model

\`env\` injects environment variables into the session; \`model\` overrides which model this project uses. An alias such as \`"opus"\` or \`"sonnet"\` keeps the file current when new models ship, whereas a pinned id goes stale. Both are optional — an empty \`{}\` is a valid settings file.

## Where it lives

Shared project rules go in \`.claude/settings.json\`; personal overrides in \`.claude/settings.local.json\` (git-ignored); global defaults in \`~/.claude/settings.json\`. For ordinary keys the most specific scope wins: managed policy, then command-line flags, then local, then project, then user. Permission rules from all scopes are merged, so a \`deny\` in any of them still blocks.

Add \`"$schema": "https://json.schemastore.org/claude-code-settings.json"\` at the top so your editor autocompletes and validates keys.

## Security notes

- \`deny\` beats \`allow\` — lean on it for secrets and destructive commands.
- Do not store API keys here; reference them via \`env\` or a separate secrets file.
- Hook commands run automatically with your privileges — read them before trusting a shared config.

Open the Claude Code settings template and ask the workspace to "deny access to the .env file" or "add a hook that runs prettier after edits", then diff the result.`,
};
