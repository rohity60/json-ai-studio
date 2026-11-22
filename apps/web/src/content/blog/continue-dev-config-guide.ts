import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'continue-dev-config-guide',
    title: 'The Continue.dev config.json Guide (and Migrating to config.yaml)',
    description:
      'How config.json sets up the Continue.dev assistant — chat models vs the tab-autocomplete model, the embeddings provider behind @codebase, context providers and custom slash commands.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['continue', 'ai', 'code-assistant', 'autocomplete'],
    readingTime: '5 min',
    aiSummary:
      'Continue.dev config.json wires up its assistant. models is the list of chat models; tabAutocompleteModel is a separate fast model for inline completions; embeddingsProvider powers @codebase retrieval; contextProviders add sources like code, diff and docs; slashCommands add custom /commands. Use a small model for autocomplete, reference API keys as secrets, and prefer local providers for sensitive code.',
    relatedTemplates: ['continue-dev-config'],
    relatedBlogs: ['mcp-json-guide', 'llm-thinking-reasoning-config'],
    faq: [
      {
        q: 'Why separate chat and autocomplete models?',
        a: 'Chat wants a strong, higher-latency model; inline autocomplete needs to be near-instant. Continue lets you pick a big model for chat and a small fast one (like Codestral) for tabAutocompleteModel.',
      },
      {
        q: 'JSON or YAML?',
        a: 'config.json is deprecated. Continue now uses config.yaml, and when both files exist it loads config.yaml and ignores config.json. Most fields map across (contextProviders becomes context, systemMessage becomes rules), but slashCommands and the top-level requestOptions/completionOptions have no YAML equivalent.',
      },
    ],
  },
  body: `Continue.dev is an open-source AI assistant for VS Code and JetBrains, and \`config.json\` is where you tell it which models to use and where to pull context from.

> **Heads up:** \`config.json\` is **deprecated**. Continue's current format is \`config.yaml\`, and if both files exist, \`config.yaml\` wins and \`config.json\` is ignored. Use this guide to read or maintain a legacy setup, and see the migration section at the end.

## Chat models vs autocomplete

\`models\` lists the models available in chat:

\`\`\`json
"models": [
  { "title": "Claude Sonnet", "provider": "anthropic", "model": "claude-sonnet-5-5", "apiKey": "\${{ secrets.ANTHROPIC_API_KEY }}" }
]
\`\`\`

\`tabAutocompleteModel\` is deliberately **separate** — inline completion needs to be fast, so people pair a strong chat model with a small one like Codestral for typing.

## Embeddings power @codebase

\`embeddingsProvider\` builds the index behind \`@codebase\` retrieval, so the assistant can answer questions about your whole repo, not just the open file.

## Context providers

\`contextProviders\` are the \`@\` sources you can pull in:

\`\`\`json
"contextProviders": [
  { "name": "code" }, { "name": "diff" }, { "name": "docs" }, { "name": "terminal" }
]
\`\`\`

Add only the ones you use — each extra provider is more noise in the prompt.

## Custom slash commands

\`slashCommands\` adds \`/\` actions in chat, like \`/edit\` or a project-specific \`/test\`.

## Migrating to config.yaml

The same setup in YAML. \`models\` becomes a single list, and each entry declares its \`roles\`:

\`\`\`yaml
name: my-assistant
version: 1.0.0
schema: v1
models:
  - name: Claude Sonnet
    provider: anthropic
    model: claude-sonnet-5-5
    apiKey: \${{ secrets.ANTHROPIC_API_KEY }}
    roles: [chat, edit, apply]
  - name: Codestral
    provider: mistral
    model: codestral-latest
    apiKey: \${{ secrets.MISTRAL_API_KEY }}
    roles: [autocomplete]
context:
  - provider: code
  - provider: diff
  - provider: terminal
\`\`\`

| config.json | config.yaml |
|---|---|
| \`models\` + \`tabAutocompleteModel\` + \`embeddingsProvider\` | one \`models\` list with \`roles\` (\`chat\`, \`autocomplete\`, \`embed\` …) |
| \`contextProviders\` | \`context\` |
| \`systemMessage\` | \`rules\` |
| \`slashCommands\` | no equivalent (use prompts) |

## Security notes

- Reference API keys as \`\${{ secrets.NAME }}\`, never inline.
- Local providers such as Ollama keep code on your machine — prefer them for sensitive repos.
- Vet third-party context providers before enabling them.

Open the Continue.dev config template and ask the workspace to "add an Ollama model for local inference" or "add the codebase context provider", then diff the result.`,
};
