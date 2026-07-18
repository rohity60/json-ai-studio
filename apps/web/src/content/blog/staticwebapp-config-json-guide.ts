import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'staticwebapp-config-json-guide',
    title: 'The staticwebapp.config.json Guide',
    description:
      'How staticwebapp.config.json controls routing, role-based authorization, SPA fallback and response overrides for Azure Static Web Apps — the settings that make client-side routing and protected sections work.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['azure', 'static-web-apps', 'routing', 'spa', 'auth'],
    readingTime: '6 min',
    aiSummary:
      'staticwebapp.config.json is the edge config for an Azure Static Web App. routes gate paths by role and do redirects/rewrites; navigationFallback rewrites unmatched navigation to the SPA shell (with static assets excluded); responseOverrides customize 401/403/404. Return 404 for protected routes and set security headers in globalHeaders.',
    relatedTemplates: ['azure-static-web-app-config'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Why does my SPA 404 on refresh?',
        a: 'Client-side routes do not exist as files. navigationFallback rewrites unmatched navigation requests to /index.html so your router takes over — but exclude static assets so images and JS still serve directly.',
      },
      {
        q: 'Where must this file live?',
        a: 'In the app root of your build output (the folder configured as app_location / output). It is served from the edge, not from your app code.',
      },
    ],
  },
  body: `\`staticwebapp.config.json\` runs at the **edge** of an Azure Static Web App — before your app code. It decides who can reach which route, where unmatched paths go, and what your error pages look like.

## Route rules: auth, redirects, rewrites

Each route can require a role, redirect, or rewrite:

\`\`\`json
"routes": [
  { "route": "/admin/*", "allowedRoles": ["administrator"] },
  { "route": "/login", "rewrite": "/.auth/login/aad" },
  { "route": "/old-path", "redirect": "/new-path", "statusCode": 301 }
]
\`\`\`

\`allowedRoles\` is enforced at the edge — stronger than checking auth in client JS alone.

## Fix the SPA refresh 404

Single-page-app routes are not files, so a refresh on \`/dashboard\` 404s unless you fall back to the shell:

\`\`\`json
"navigationFallback": {
  "rewrite": "/index.html",
  "exclude": ["/images/*.{png,jpg,gif}", "/css/*", "/js/*"]
}
\`\`\`

The \`exclude\` list is essential — without it, a missing image would also return your HTML.

## Custom error pages

\`responseOverrides\` turns raw status codes into friendly pages or redirects:

\`\`\`json
"responseOverrides": {
  "401": { "redirect": "/login", "statusCode": 302 },
  "404": { "rewrite": "/404.html" }
}
\`\`\`

## Security headers everywhere

Put \`Content-Security-Policy\` and \`X-Content-Type-Options\` in \`globalHeaders\` so they apply to every response.

## Security notes

- Return **404** (not 403) for protected admin routes so their existence is not revealed.
- Auth provider secrets go in application settings, never in this file.

Open the Static Web App config template and ask the workspace to "add a route that requires the authenticated role" or "add a Content-Security-Policy header", then diff the result.`,
};
