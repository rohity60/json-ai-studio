import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'auth0-client-config',
    slug: 'auth0-client-config',
    title: 'Auth0 Application (Client) Config',
    description:
      'An Auth0 application/client configuration export — callback URLs, grant types, token settings and JWT config — for a regular web app.',
    category: 'Authentication',
    provider: 'Auth0',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['auth0', 'oauth', 'oidc', 'authentication', 'jwt'],
    schemaVersion: '1',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain each setting in this Auth0 config',
      'Add a production callback URL',
      'Switch token endpoint auth to none for a SPA',
      'Enable refresh token rotation',
    ],
    relatedTemplates: ['keycloak-realm', 'firebase-config'],
    relatedBlogs: [],
    purpose:
      'Configure an Auth0 application: how it authenticates, where it redirects, and how tokens are issued.',
    whenToUse:
      'Managing an Auth0 tenant as code via the Deploy CLI / Management API, or reviewing an application export.',
    requiredFields: [
      'name — the application display name',
      'app_type — regular_web, spa, native, or non_interactive',
      'callbacks — allowed redirect URIs',
    ],
    optionalFields: [
      'allowed_logout_urls — post-logout redirects',
      'grant_types — enabled OAuth grants',
      'jwt_configuration — token lifetime and signing alg',
      'oidc_conformant — enable OIDC-conformant behavior',
    ],
    bestPractices: [
      'Enable oidc_conformant on new applications.',
      'Use RS256 for token signing, not HS256.',
      'List exact callback/logout URLs — no wildcards in production.',
    ],
    security: [
      'Never store client_secret in a public (SPA/native) app.',
      'Restrict callbacks to your own domains only.',
      'Prefer authorization_code + PKCE over implicit grant.',
    ],
  },
  json: {
    name: 'My Web App',
    app_type: 'regular_web',
    oidc_conformant: true,
    callbacks: [
      'https://app.example.com/callback',
      'http://localhost:3000/callback',
    ],
    allowed_logout_urls: ['https://app.example.com'],
    web_origins: ['https://app.example.com'],
    grant_types: ['authorization_code', 'refresh_token'],
    token_endpoint_auth_method: 'client_secret_post',
    jwt_configuration: {
      alg: 'RS256',
      lifetime_in_seconds: 3600,
    },
    refresh_token: {
      rotation_type: 'rotating',
      expiration_type: 'expiring',
      token_lifetime: 2592000,
    },
  },
};
