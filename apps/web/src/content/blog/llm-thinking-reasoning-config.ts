import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'llm-thinking-reasoning-config',
    title: 'Setting Thinking / Reasoning Config Across LLM Providers',
    description:
      'How to configure reasoning effort and thinking budgets for Anthropic Claude, OpenAI, and Google Gemini — and why the same provider needs different config for different models.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['llm', 'ai', 'anthropic', 'openai', 'gemini', 'reasoning', 'api'],
    readingTime: '7 min',
    aiSummary:
      'Every major provider now exposes a "how hard should the model think" knob, but the JSON differs by provider AND by model. Claude uses adaptive thinking plus output_config.effort; budget_tokens is removed on current models, and Opus 5.5 / Fable cannot turn thinking off. OpenAI uses reasoning_effort, accepted only by reasoning models, with level sets that vary per model. Gemini 3 uses thinkingConfig.thinkingLevel; Gemini 2.5 uses thinkingBudget (0 off, -1 dynamic). The recurring trap: a request body valid on one model returns a 400 on another from the same provider.',
    relatedTemplates: ['anthropic-messages-request', 'openai-chat-request'],
    relatedBlogs: ['llm-structured-outputs-json', 'json-schema-guide'],
    faq: [
      {
        q: 'Why does my thinking config return a 400 on one model but work on another?',
        a: 'Reasoning config is model-specific, not just provider-specific. Anthropic removed budget_tokens on every current Claude model (it 400s), OpenAI only accepts reasoning_effort on reasoning models, and Gemini 3 replaced thinkingBudget with thinkingLevel, whose allowed levels differ per model. Always match the config to the exact model.',
      },
      {
        q: 'How do I turn thinking OFF?',
        a: 'Claude: it depends on the model. Opus 5.5 and Fable 5.x reject {"type":"disabled"}, so use low effort. Sonnet 5.5 takes {"type":"between_tools"}. Opus 4.7/4.8 still accept disabled. OpenAI: reasoning_effort "none" on newer GPT-5.x models, or a non-reasoning model. Gemini: thinkingBudget 0 on 2.5 Flash; Gemini 3 only lets you drop to its lowest thinkingLevel.',
      },
      {
        q: 'What is the difference between an effort level and a token budget?',
        a: 'A token budget (Gemini thinkingBudget, legacy Claude budget_tokens) caps thinking tokens directly. An effort level (Claude output_config.effort, OpenAI reasoning_effort, Gemini 3 thinkingLevel) is a coarse low/medium/high dial the model interprets. Modern APIs favor effort levels.',
      },
    ],
  },
  body: `Every major model provider now lets you tune **how hard the model thinks** before it answers. More thinking usually means better reasoning at the cost of latency and tokens. The catch: the JSON that controls it differs not just between providers, but between **models from the same provider**. A body that works on one model can return a \`400\` on the next.

This post is a field guide to the current shapes.

## The one rule that saves you

**Reasoning config is model-specific.** Do not assume a payload that worked last month, or on a sibling model, still validates. Providers add, rename, and remove these fields per model generation. Match the config to the exact model id you are calling.

## Anthropic — Claude

Claude uses a top-level \`thinking\` field on the Messages API, and controls depth with \`output_config.effort\`.

**Current models (Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.2):** thinking is adaptive and **on by default**. The model decides how much to think, and \`effort\` sets how hard it tries.

\`\`\`json
{
  "model": "claude-opus-5-5",
  "max_tokens": 16000,
  "thinking": { "type": "adaptive", "display": "summarized" },
  "output_config": { "effort": "high" },
  "messages": [{ "role": "user", "content": "..." }]
}
\`\`\`

- \`effort\` accepts \`low\` / \`medium\` / \`high\` / \`xhigh\` / \`max\`. Defaults differ by model: **Opus 5.5 and Haiku 5.5 default to \`medium\`**, most others to \`high\`. Set it explicitly.
- \`budget_tokens\` is **removed** on every current model. Sending \`{"type":"enabled","budget_tokens":N}\` returns a **400**. It still works, deprecated, only on Opus 4.6 / Sonnet 4.6.
- **Turning thinking off is model-specific.** \`{"type":"disabled"}\` returns a 400 on Opus 5.5, Sonnet 5.5 and Fable 5.x. On Opus 5.5 and Fable, lower \`effort\` instead. Sonnet 5.5 has \`{"type":"between_tools"}\`, accepted only at effort \`high\` or below. Older Opus 4.7/4.8 still accept \`disabled\`, and there omitting \`thinking\` means no thinking at all.
- \`display\` defaults to \`"omitted"\`: thinking happens and is billed, but the text comes back empty. Set \`"summarized"\` if you show reasoning to users.
- \`temperature\`, \`top_p\` and \`top_k\` are rejected on current models, so don't carry them over from older request bodies.

**Older models (Haiku 4.5, Sonnet 4.5):** the classic token budget still applies.

\`\`\`json
{ "thinking": { "type": "enabled", "budget_tokens": 8000 } }
\`\`\`

\`budget_tokens\` must be less than \`max_tokens\` (minimum 1024).

## OpenAI

OpenAI exposes \`reasoning_effort\` (Chat Completions) — or \`reasoning: { "effort": ... }\` on the Responses API.

\`\`\`json
{
  "model": "gpt-5.6",
  "reasoning_effort": "medium",
  "messages": [{ "role": "user", "content": "..." }]
}
\`\`\`

Two model-specific traps:

- **Only reasoning models accept it.** Sending \`reasoning_effort\` to a non-reasoning chat model is rejected, and reasoning models in turn reject \`temperature\`.
- **The level set varies by model.** The original GPT-5 used \`minimal\` / \`low\` / \`medium\` / \`high\`. Later models replaced \`minimal\` with \`none\` and added a top tier (\`xhigh\`). Check the model page before you hardcode a level.

## Google Gemini

Gemini uses a \`thinkingConfig\` block inside \`generationConfig\`, and the field changed between generations.

**Gemini 3 and later:** use \`thinkingLevel\`.

\`\`\`json
{
  "generationConfig": {
    "thinkingConfig": { "thinkingLevel": "high", "includeThoughts": true }
  }
}
\`\`\`

- Level sets vary by model: Pro variants take \`low\` / \`high\`; some Flash variants add \`minimal\` and \`medium\`. An unsupported level is rejected.
- \`includeThoughts: true\` returns a thought summary.

**Gemini 2.5:** use \`thinkingBudget\`. \`0\` disables thinking (Flash only; 2.5 Pro can't fully disable it), and \`-1\` lets the model pick the budget.

\`\`\`json
{ "generationConfig": { "thinkingConfig": { "thinkingBudget": -1 } } }
\`\`\`

## Cheat sheet

| Provider / generation | Field | Turn off | Dial |
|---|---|---|---|
| Claude Opus 5.5 / Fable 5.x | \`thinking: {type:"adaptive"}\` (or omit) | not possible: lower \`effort\` | \`output_config.effort\` |
| Claude Sonnet 5.5 | \`thinking: {type:"adaptive"}\` | \`{type:"between_tools"}\` | \`output_config.effort\` |
| Claude Haiku 4.5 / older | \`thinking: {type:"enabled", budget_tokens}\` | omit | \`budget_tokens\` |
| OpenAI GPT-5.x | \`reasoning_effort\` | \`none\` (newer models) | \`none…xhigh\` (varies) |
| Gemini 3+ | \`thinkingConfig.thinkingLevel\` | lowest level the model allows | \`minimal…high\` (varies) |
| Gemini 2.5 | \`thinkingConfig.thinkingBudget\` | \`0\` (Flash only) | \`-1\` dynamic / token count |

## Practical advice

- **Pin the config to the model id in code**, not to a provider. A per-model lookup beats a single shared default.
- **Start at medium/high** for reasoning-sensitive work, drop to low/minimal for latency-sensitive paths.
- **Handle the 400.** When you upgrade a model, re-check the thinking block first — it's the field most likely to have changed.

Paste any of these request bodies into the workspace and ask the AI to "explain each field" or "convert this to the Gemini shape" — it's the fastest way to port a payload from one provider to another.`,
};
