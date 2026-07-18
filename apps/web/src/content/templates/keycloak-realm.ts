import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'keycloak-realm',
    slug: 'keycloak-realm',
    title: 'Keycloak Realm Export',
    description:
      'A trimmed Keycloak realm export with a client, token lifetimes and password policy — the shape you import to bootstrap a realm.',
    category: 'Authentication',
    provider: 'Keycloak',
    difficulty: 'advanced',
    estimatedReadTime: '6 min',
    tags: ['keycloak', 'oidc', 'sso', 'authentication', 'realm'],
    schemaVersion: '1',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Enable user registration',
      'Add a public client for a SPA',
      'Tighten the password policy',
      'Shorten the access token lifespan',
    ],
    relatedTemplates: ['auth0-client-config'],
    relatedBlogs: [],
    purpose:
      'Define a Keycloak realm — its clients, token settings and policies — as an importable JSON export.',
    whenToUse:
      'Bootstrapping a realm via `kc.sh import`, or version-controlling realm configuration.',
    requiredFields: [
      'realm — the realm name',
      'enabled — whether the realm is active',
      'clients — the applications registered in the realm',
    ],
    optionalFields: [
      'accessTokenLifespan / ssoSessionIdleTimeout — token/session timing',
      'passwordPolicy — enforced password rules',
      'roles — realm and client roles',
    ],
    bestPractices: [
      'Keep publicClient=false + a confidential secret for server apps.',
      'Set standardFlowEnabled (auth code) and disable implicit/direct grant.',
      'Enforce a strong passwordPolicy.',
    ],
    security: [
      'Never commit real client secrets — export with secrets scrubbed.',
      'Restrict redirectUris to exact URLs.',
      'Keep access token lifespans short; rely on refresh tokens.',
    ],
  },
  json: {
    realm: 'example',
    enabled: true,
    sslRequired: 'external',
    accessTokenLifespan: 300,
    ssoSessionIdleTimeout: 1800,
    passwordPolicy: 'length(12) and upperCase(1) and digits(1)',
    clients: [
      {
        clientId: 'web-app',
        enabled: true,
        publicClient: false,
        standardFlowEnabled: true,
        directAccessGrantsEnabled: false,
        redirectUris: ['https://app.example.com/*'],
        webOrigins: ['https://app.example.com'],
        protocol: 'openid-connect',
      },
    ],
    roles: {
      realm: [{ name: 'user' }, { name: 'admin' }],
    },
  },
};
