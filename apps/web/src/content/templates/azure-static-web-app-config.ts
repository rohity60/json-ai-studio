import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'azure-static-web-app-config',
    slug: 'azure-static-web-app-config',
    title: 'Azure Static Web Apps — staticwebapp.config.json',
    description:
      'The staticwebapp.config.json that controls routing, role-based authorization, custom auth, fallback for client-side routers, and response overrides for an Azure Static Web App.',
    category: 'Cloud',
    provider: 'Azure',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['azure', 'static-web-apps', 'routing', 'auth', 'spa'],
    schemaVersion: 'staticwebapp-config-v1',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a route that requires the authenticated role',
      'Redirect /old-path to /new-path',
      'Add a Content-Security-Policy header',
      'Block access to /api during maintenance',
    ],
    relatedTemplates: ['azure-app-service-settings', 'azure-functions-host-json'],
    relatedBlogs: ['staticwebapp-config-json-guide'],
    purpose:
      'Configure the edge behavior of an Azure Static Web App: which routes need which roles, how unmatched routes fall back to the SPA shell, and how errors are handled.',
    whenToUse:
      'Deploying a single-page app (React/Vue/Angular) to Azure Static Web Apps that needs client-side routing, protected sections, or custom auth providers.',
    requiredFields: [
      'routes — per-path rules for auth, redirects and rewrites',
      'navigationFallback — the SPA fallback for unmatched navigation requests',
    ],
    optionalFields: [
      'responseOverrides — custom pages for 401/403/404 responses',
      'auth — custom identity provider registrations',
      'globalHeaders — headers applied to every response',
      'mimeTypes — extension-to-content-type mappings',
    ],
    bestPractices: [
      'Exclude static assets from navigationFallback so images and JS are served directly.',
      'Gate protected routes with allowedRoles rather than checking auth in client code alone.',
      'Set security headers (CSP, X-Content-Type-Options) in globalHeaders.',
    ],
    security: [
      'Do not place client secrets in this file; auth provider secrets go in application settings.',
      'Return 404 (not 403) for protected admin routes to avoid revealing their existence.',
      'Keep a strict Content-Security-Policy to limit XSS blast radius.',
    ],
  },
  json: {
    routes: [
      { route: '/admin/*', allowedRoles: ['administrator'] },
      { route: '/api/*', allowedRoles: ['authenticated'] },
      { route: '/login', rewrite: '/.auth/login/aad' },
      { route: '/logout', redirect: '/.auth/logout' },
      { route: '/old-path', redirect: '/new-path', statusCode: 301 },
    ],
    navigationFallback: {
      rewrite: '/index.html',
      exclude: ['/images/*.{png,jpg,gif}', '/css/*', '/js/*'],
    },
    responseOverrides: {
      '401': { redirect: '/login', statusCode: 302 },
      '403': { rewrite: '/403.html' },
      '404': { rewrite: '/404.html' },
    },
    globalHeaders: {
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'self'; img-src 'self' data:",
    },
    mimeTypes: {
      '.json': 'application/json',
      '.webmanifest': 'application/manifest+json',
    },
  },
};
