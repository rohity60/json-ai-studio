import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'vscode-settings',
    slug: 'vscode-settings',
    title: 'VS Code settings.json (Team Baseline)',
    description:
      'A shared VS Code settings.json enforcing format-on-save, Prettier, consistent tabs and sensible editor defaults across a team.',
    category: 'IDE',
    provider: 'VS Code',
    difficulty: 'beginner',
    estimatedReadTime: '4 min',
    tags: ['vscode', 'ide', 'settings', 'prettier', 'eslint', 'formatting'],
    schemaVersion: '1.0',
    featured: true,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Enable format on save',
      'Add Python-specific formatting settings',
      'Turn on ESLint auto-fix on save',
      'Set the default formatter to Prettier for JSON',
    ],
    relatedTemplates: [],
    relatedBlogs: [],
    purpose:
      'Standardise editor behaviour — formatting, whitespace, and save actions — so every developer produces identical diffs.',
    whenToUse:
      'Commit as .vscode/settings.json in a repo to give the whole team consistent, opinionated editor defaults.',
    requiredFields: [
      'No fields are strictly required — every key is optional and overrides a default.',
    ],
    optionalFields: [
      'editor.formatOnSave — format automatically on save',
      'editor.defaultFormatter — which extension formats code',
      'editor.tabSize / insertSpaces — indentation',
      '"[language]" blocks — per-language overrides',
    ],
    bestPractices: [
      'Commit workspace settings under .vscode/ so they apply to everyone.',
      'Set per-language formatters with "[json]", "[typescript]" blocks.',
      'Enable codeActionsOnSave for ESLint auto-fix.',
    ],
    security: [
      'Never put secrets or tokens in settings.json — it is committed to git.',
      'Be cautious enabling settings that auto-run tasks or code on folder open.',
    ],
  },
  json: {
    'editor.formatOnSave': true,
    'editor.defaultFormatter': 'esbenp.prettier-vscode',
    'editor.tabSize': 2,
    'editor.insertSpaces': true,
    'editor.rulers': [100],
    'files.trimTrailingWhitespace': true,
    'files.insertFinalNewline': true,
    'editor.codeActionsOnSave': { 'source.fixAll.eslint': 'explicit' },
    '[json]': { 'editor.defaultFormatter': 'esbenp.prettier-vscode' },
    '[typescript]': { 'editor.defaultFormatter': 'esbenp.prettier-vscode' },
  },
};
