import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'anthropic-messages-request',
    slug: 'anthropic-messages-request',
    title: 'Anthropic Messages API Request',
    description:
      'A request body for the Anthropic Messages API (POST /v1/messages) with adaptive thinking, a system prompt, tools and a multi-turn conversation.',
    category: 'AI',
    provider: 'Anthropic',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['anthropic', 'claude', 'llm', 'ai', 'messages-api', 'tools'],
    schemaVersion: '2023-06-01',
    featured: true,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a system prompt',
      'Add a tool for getting the weather',
      'Enable streaming',
      'Raise max_tokens for a long response',
    ],
    relatedTemplates: ['openai-chat-request'],
    relatedBlogs: ['llm-thinking-reasoning-config', 'llm-structured-outputs-json'],
    purpose:
      'Call Claude via the Messages API — the single endpoint for chat, tool use and structured output.',
    whenToUse:
      'Building an application on Claude: pass this JSON as the body of POST https://api.anthropic.com/v1/messages.',
    requiredFields: [
      'model — the Claude model id, e.g. claude-opus-5-5',
      'max_tokens — the hard cap on output tokens',
      'messages — the conversation turns (user/assistant)',
    ],
    optionalFields: [
      'system — a top-level system prompt (string or blocks)',
      'thinking — {"type":"adaptive"} lets Claude decide how much to think (on by default on current models)',
      'output_config.effort — low / medium / high / xhigh / max; Opus 5.5 defaults to medium',
      'output_config.format — {"type":"json_schema","schema":{…}} for schema-guaranteed JSON output',
      'tools — function definitions Claude may call',
      'stream — set true to receive server-sent events',
    ],
    bestPractices: [
      'Default to model "claude-opus-5-5"; use claude-sonnet-5-5 or claude-haiku-5-5 for cheaper routes.',
      'Use thinking {"type":"adaptive"} — budget_tokens returns a 400 on current models; tune depth with output_config.effort.',
      'Do not send temperature/top_p/top_k or an assistant prefill — current models reject them with a 400.',
      'Stream when max_tokens is large to avoid HTTP timeouts.',
    ],
    security: [
      'Send your key in the x-api-key header, never in this body.',
      'Keep API keys server-side; never ship them to a browser.',
      'Do not put secrets in the prompt — they are sent to the API and logged app-side.',
    ],
  },
  json: {
    model: 'claude-opus-5-5',
    max_tokens: 16000,
    system: 'You are a concise assistant. Answer directly.',
    thinking: { type: 'adaptive' },
    output_config: { effort: 'high' },
    messages: [
      { role: 'user', content: 'What is the capital of France?' },
      { role: 'assistant', content: 'Paris.' },
      { role: 'user', content: 'And its population, roughly?' },
    ],
    tools: [
      {
        name: 'get_population',
        description: 'Get the approximate population of a city.',
        input_schema: {
          type: 'object',
          properties: {
            city: { type: 'string', description: 'City name' },
          },
          required: ['city'],
          additionalProperties: false,
        },
        strict: true,
      },
    ],
  },
};
