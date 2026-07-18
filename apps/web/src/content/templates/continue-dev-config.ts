import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'continue-dev-config',
    slug: 'continue-dev-config',
    title: 'Continue.dev config.json',
    description:
      'A Continue.dev config.json wiring up a chat model, a tab-autocomplete model, an embeddings provider, context providers and a custom slash command — the setup for the open-source AI code assistant.',
    category: 'AI',
    provider: 'Continue',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['continue', 'ai', 'code-assistant', 'autocomplete', 'vscode'],
    schemaVersion: 'continue-config-v1',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add an Ollama model for local inference',
      'Add the codebase context provider',
      'Change the autocomplete model to a smaller one',
      'Add a custom /test slash command',
    ],
    relatedTemplates: ['claude-code-settings', 'mcp-server-config'],
    relatedBlogs: ['continue-dev-config-guide'],
    purpose:
      'Configure the Continue.dev assistant — which models power chat and autocomplete, where it pulls context from, and which slash commands are available in the editor.',
    whenToUse:
      'Setting up Continue.dev in VS Code or JetBrains: mixing a strong chat model with a fast local autocomplete model, and tailoring context providers to your repo.',
    requiredFields: [
      'models — the list of chat models, each with title, provider and model',
    ],
    optionalFields: [
      'tabAutocompleteModel — a fast model dedicated to inline completions',
      'embeddingsProvider — powers @codebase retrieval',
      'contextProviders — sources like code, docs, diff, terminal',
      'slashCommands — custom /commands surfaced in chat',
    ],
    bestPractices: [
      'Use a small, fast model for tabAutocompleteModel and a strong one for chat.',
      'Reference API keys with ${{ secrets.NAME }} instead of pasting them inline.',
      'Add only the context providers you use to keep prompts focused.',
    ],
    security: [
      'Never commit real API keys; use Continue secret references or environment variables.',
      'Local providers (Ollama) keep code on your machine — prefer them for sensitive repos.',
      'Review third-party context providers before enabling them.',
    ],
  },
  json: {
    models: [
      {
        title: 'Claude Sonnet',
        provider: 'anthropic',
        model: 'claude-sonnet-4-5',
        apiKey: '${{ secrets.ANTHROPIC_API_KEY }}',
      },
    ],
    tabAutocompleteModel: {
      title: 'Codestral',
      provider: 'mistral',
      model: 'codestral-latest',
      apiKey: '${{ secrets.MISTRAL_API_KEY }}',
    },
    embeddingsProvider: {
      provider: 'openai',
      model: 'text-embedding-3-small',
      apiKey: '${{ secrets.OPENAI_API_KEY }}',
    },
    contextProviders: [
      { name: 'code' },
      { name: 'diff' },
      { name: 'docs' },
      { name: 'terminal' },
    ],
    slashCommands: [
      { name: 'edit', description: 'Edit selected code' },
      { name: 'comment', description: 'Write comments for the selected code' },
    ],
  },
};
