import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'claude-code-settings',
    slug: 'claude-code-settings',
    title: 'Claude Code settings.json',
    description:
      'A .claude/settings.json for Claude Code — permission allow/deny/ask rules, a PostToolUse hook, environment variables and a model override — the file that governs how the agent behaves in a repo.',
    category: 'AI',
    provider: 'Claude Code',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['claude-code', 'ai', 'agent', 'permissions', 'hooks'],
    schemaVersion: 'claude-code-settings-v1',
    featured: true,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Allow all npm test commands without prompting',
      'Add a hook that runs prettier after edits',
      'Deny access to the .env file',
      'Ask before any git push',
    ],
    relatedTemplates: ['mcp-server-config', 'continue-dev-config'],
    relatedBlogs: ['claude-code-settings-guide'],
    purpose:
      'Control how Claude Code operates in a project — which tools run without prompting, what is always blocked, and what shell commands fire on lifecycle events.',
    whenToUse:
      'Standardizing agent behavior for a repo: fewer permission prompts for safe commands, hard denies for secrets, and hooks that keep formatting or tests consistent.',
    requiredFields: [
      'No field is strictly required; an empty {} is valid. permissions is the most common.',
    ],
    optionalFields: [
      'permissions — allow / deny / ask arrays of tool-pattern rules',
      'hooks — commands run on events like PostToolUse or Stop',
      'env — environment variables injected into the session',
      'model — override the model used in this project',
    ],
    bestPractices: [
      'Allow only narrow, safe command patterns (e.g. Bash(npm run test:*)), not broad wildcards.',
      'Keep secret files in deny (Read(./.env)) so the agent never reads them.',
      'Use ask for irreversible actions like git push instead of allow.',
    ],
    security: [
      'deny rules win over allow — put secret paths and destructive commands there.',
      'Do not put API keys in this file; use env references or a separate secrets file.',
      'Review hook commands carefully — they run automatically with your shell privileges.',
    ],
  },
  json: {
    $schema: 'https://json.schemastore.org/claude-code-settings.json',
    permissions: {
      allow: ['Bash(npm run test:*)', 'Bash(npm run lint:*)', 'Read(./src/**)'],
      ask: ['Bash(git push:*)'],
      deny: ['Read(./.env)', 'Bash(rm -rf:*)'],
    },
    env: {
      NODE_ENV: 'development',
    },
    model: 'claude-sonnet-4-5',
    hooks: {
      PostToolUse: [
        {
          matcher: 'Edit|Write',
          hooks: [
            {
              type: 'command',
              command: 'npx prettier --write "$CLAUDE_FILE_PATHS"',
            },
          ],
        },
      ],
    },
  },
};
