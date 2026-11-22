import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'openai-chat-request',
    slug: 'openai-chat-request',
    title: 'OpenAI Chat Completions Request',
    description:
      'A request body for the OpenAI Chat Completions API with a system message, a multi-turn conversation and a tool (function) definition.',
    category: 'AI',
    provider: 'OpenAI',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['openai', 'gpt', 'llm', 'ai', 'chat-completions', 'tools'],
    schemaVersion: 'v1',
    featured: false,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a system message',
      'Add a function tool for the weather',
      'Enable streaming',
      'Force a JSON response format',
    ],
    relatedTemplates: ['anthropic-messages-request'],
    relatedBlogs: ['llm-thinking-reasoning-config', 'llm-structured-outputs-json'],
    purpose:
      'Call an OpenAI chat model — the request shape for POST /v1/chat/completions.',
    whenToUse:
      'Building on OpenAI: pass this JSON as the body of the Chat Completions endpoint.',
    requiredFields: [
      'model — the model id',
      'messages — the conversation, each with a role and content',
    ],
    optionalFields: [
      'tools — function definitions the model may call',
      'temperature — sampling randomness (0–2)',
      'response_format — e.g. {"type":"json_object"}',
      'stream — set true for server-sent events',
    ],
    bestPractices: [
      'Start the conversation with a system message to set behavior.',
      'Keep tool schemas strict with required fields.',
      'Set response_format {type:"json_schema", json_schema:{strict:true,…}} when you need machine-parseable output.',
      'reasoning_effort level sets vary per model (e.g. none…xhigh); reasoning models reject temperature, so leave it out.',
    ],
    security: [
      'Send the key in the Authorization: Bearer header, not this body.',
      'Keep keys server-side; never expose them in a browser.',
      'Avoid putting secrets in prompts.',
    ],
  },
  json: {
    model: 'gpt-5.6',
    reasoning_effort: 'medium',
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'What is the capital of France?' },
      { role: 'assistant', content: 'Paris.' },
      { role: 'user', content: 'Give me its population as JSON.' },
    ],
    tools: [
      {
        type: 'function',
        function: {
          name: 'get_population',
          description: 'Get the approximate population of a city.',
          parameters: {
            type: 'object',
            properties: {
              city: { type: 'string', description: 'City name' },
            },
            required: ['city'],
            additionalProperties: false,
          },
          strict: true,
        },
      },
    ],
  },
};
