import type { MetadataRoute } from 'next';

// AI crawlers we explicitly welcome so assistants can discover, read and cite
// the site. NOTE: the production robots.txt is also shaped by Cloudflare's
// managed AI-bot rules — AI crawling must be allowed in the Cloudflare
// dashboard too, otherwise its per-bot Disallow overrides these origin rules.
const AI_BOTS = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-Web',
  'anthropic-ai',
  'PerplexityBot',
  'Google-Extended',
  'Applebot-Extended',
  'CCBot',
  'cohere-ai',
  'Amazonbot',
  'Bytespider',
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: '*', allow: '/', disallow: '/api/' },
      // /studio is the client-only app shell — no crawlable content, so keep AI
      // bots on the marketing/content pages and out of it and the API.
      { userAgent: AI_BOTS, allow: '/', disallow: ['/api/', '/studio'] },
    ],
    sitemap: 'https://jsonaistudio.com/sitemap.xml',
  };
}
