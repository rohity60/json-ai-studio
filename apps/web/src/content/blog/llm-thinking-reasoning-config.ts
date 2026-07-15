import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'llm-thinking-reasoning-config',
    title: 'Setting Thinking / Reasoning Config Across LLM Providers',
    description:
      'How to configure reasoning effort and thinking budgets for Anthropic Claude, OpenAI, and Google Gemini — and why the same provider needs different config for different models.',
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    tags: ['llm', 'ai', 'anthropic', 'openai', 'gemini', 'reasoning', 'api'],
    readingTime: '7 min',
    aiSummary:
      'Every major provider now exposes a "how hard should the model think" knob, but the JSON differs by provider AND by model. Claude uses thinking + effort (and Fable 5 has thinking always on). OpenAI uses reasoning_effort, accepted only by reasoning models, with level sets that vary per model. Gemini uses thinkingConfig.thinkingBudget (0 off, -1 dynamic). The recurring trap: a request body valid on one model returns a 400 on another from the same provider.',
    relatedTemplates: ['anthropic-messages-request', 'openai-chat-request'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Why does my thinking config return a 400 on one model but work on another?',
        a: 'Reasoning config is model-specific, not just provider-specific. Anthropic removed budget_tokens on Opus 4.7/4.8 and Sonnet 5 (it 400s), OpenAI only accepts reasoning_effort on reasoning models, and Gemini\'s valid thinkingBudget range differs per model. Always match the config to the exact model.',
      },
      {
        q: 'How do I turn thinking OFF?',
        a: 'Claude: thinking {"type":"disabled"} on most models (but Fable 5 rejects it — thinking is always on there). OpenAI: use a non-reasoning model, or the lowest effort the model allows. Gemini: set thinkingBudget to 0 (only on models that allow disabling, e.g. 2.5 Flash).',
      },
      {
        q: 'What is the difference between an effort level and a token budget?',
        a: 'A token budget (Gemini thinkingBudget, legacy Claude budget_tokens) caps thinking tokens directly. An effort level (Claude output_config.effort, OpenAI reasoning_effort) is a coarse low/medium/high dial the model interprets. Modern APIs favor effort levels.',
      },
    ],
  },
  body: `Every major model provider now lets you tune **how hard the model thinks** before it answers. More thinking usually means better reasoning at the cost of latency and tokens. The catch: the JSON that controls it differs not just between providers, but between **models from the same provider**. A body that works on one model can return a \`400\` on the next.

This post is a field guide to the current shapes.

## The one rule that saves you

**Reasoning config is model-specific.** Do not assume a payload that worked last month, or on a sibling model, still validates. Providers add, rename, and remove these fields per model generation. Match the config to the exact model id you are calling.

## Anthropic — Claude

Claude uses a top-level \`thinking\` field on the Messages API, and controls depth with \`output_config.effort\`.

**Current models (Opus 4.8 / 4.7, Sonnet 5, and the 4.6 family):** use adaptive thinking — the model decides how much to think.

\`\`\`json
{
  "model": "claude-opus-4-8",
  "max_tokens": 4096,
  "thinking": { "type": "adaptive" },
  "output_config": { "effort": "high" },
  "messages": [{ "role": "user", "content": "..." }]
}
\`\`\`

- \`effort\` accepts \`low\` / \`medium\` / \`high\` / \`xhigh\` / \`max\`.
- \`budget_tokens\` was **removed** on Opus 4.7/4.8 and Sonnet 5 — sending \`{"type":"enabled","budget_tokens":N}\` returns a **400**. It is only deprecated (still works) on Opus 4.6 / Sonnet 4.6.
- On Opus 4.7/4.8, omitting \`thinking\` runs **without** thinking — set \`{"type":"adaptive"}\` explicitly. On Sonnet 5 the default is adaptive-on.

**Claude Fable 5** is the exception that proves the model-specific rule: **thinking is always on**. Sending \`{"type":"disabled"}\` — accepted on Opus — returns a **400** here. Omit the field entirely and control depth with \`effort\`.

**Older models (Sonnet 4.5, Haiku 4.5):** the classic token budget still applies.

\`\`\`json
{ "thinking": { "type": "enabled", "budget_tokens": 8000 } }
\`\`\`

\`budget_tokens\` must be less than \`max_tokens\` (minimum 1024). To see a readable trace, add \`"display": "summarized"\` — the default on the newest models is \`"omitted"\` (thinking happens, but the text comes back empty).

## OpenAI

OpenAI exposes \`reasoning_effort\` (Chat Completions) — or \`reasoning: { "effort": ... }\` on the Responses API.

\`\`\`json
{
  "model": "gpt-5",
  "reasoning_effort": "medium",
  "messages": [{ "role": "user", "content": "..." }]
}
\`\`\`

Two model-specific traps:

- **Only reasoning models accept it.** Sending \`reasoning_effort\` to a non-reasoning chat model is rejected.
- **The level set varies by model.** GPT-5 supports \`minimal\` / \`low\` / \`medium\` / \`high\`; newer models in the family add \`none\` and \`xhigh\`; some pro variants accept only \`high\`. Don't hardcode a level without checking it's valid for that specific model.

## Google Gemini

Gemini uses a \`thinkingConfig\` block inside \`generationConfig\`.

\`\`\`json
{
  "generationConfig": {
    "thinkingConfig": {
      "thinkingBudget": -1,
      "includeThoughts": true
    }
  }
}
\`\`\`

- \`thinkingBudget\`: \`0\` disables thinking, \`-1\` enables **dynamic** thinking (the model picks the budget), or pass an explicit token count.
- \`includeThoughts\`: \`true\` returns a thought summary.
- **Per-model ranges differ.** Gemini 2.5 Flash can disable thinking (\`0\`); 2.5 Pro cannot fully disable it. Gemini 3 introduces a \`thinkingLevel\` parameter and recommends it over \`thinkingBudget\`.

## Cheat sheet

| Provider | Field | Turn off | Dial |
|---|---|---|---|
| Anthropic (4.6+) | \`thinking: {type:"adaptive"}\` | \`{type:"disabled"}\`* | \`output_config.effort\` |
| Anthropic (older) | \`thinking: {type:"enabled", budget_tokens}\` | \`{type:"disabled"}\` | \`budget_tokens\` |
| OpenAI | \`reasoning_effort\` | non-reasoning model | \`minimal…high\` (varies) |
| Gemini | \`thinkingConfig.thinkingBudget\` | \`0\`* | \`-1\` dynamic / token count |

\\* Not on every model — Claude Fable 5 has thinking always on; Gemini 2.5 Pro can't fully disable it.

## Practical advice

- **Pin the config to the model id in code**, not to a provider. A per-model lookup beats a single shared default.
- **Start at medium/high** for reasoning-sensitive work, drop to low/minimal for latency-sensitive paths.
- **Handle the 400.** When you upgrade a model, re-check the thinking block first — it's the field most likely to have changed.

Paste any of these request bodies into the workspace and ask the AI to "explain each field" or "convert this to the Gemini shape" — it's the fastest way to port a payload from one provider to another.`,
};
