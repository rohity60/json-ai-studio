import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'azure-app-service-settings',
    slug: 'azure-app-service-settings',
    title: 'Azure App Service — Application Settings',
    description:
      'The JSON bulk-edit format for App Service application settings and connection strings — the array you paste into the Advanced edit blade to manage a web app’s environment in one shot.',
    category: 'Cloud',
    provider: 'Azure',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['azure', 'app-service', 'web-app', 'configuration', 'env'],
    schemaVersion: 'app-settings-v1',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a setting for NODE_ENV set to production',
      'Mark the database connection string as a slot setting',
      'Add Application Insights connection string',
      'Enable run-from-package deployment',
    ],
    relatedTemplates: ['azure-functions-host-json', 'azure-static-web-app-config'],
    relatedBlogs: ['azure-app-service-settings-guide'],
    purpose:
      'Bulk-manage a Web App’s environment variables and connection strings as one JSON array instead of editing rows by hand.',
    whenToUse:
      'Migrating settings between slots or environments, code-reviewing config changes, or seeding a new App Service from a known-good baseline.',
    requiredFields: [
      'name — the setting key exposed as an environment variable',
      'value — the setting value',
      'slotSetting — whether the value is pinned to the deployment slot',
    ],
    optionalFields: [
      'WEBSITE_* keys — platform behavior toggles (run-from-package, node version)',
      'connection-string entries — surfaced with provider-specific prefixes',
    ],
    bestPractices: [
      'Mark environment-specific values (DB, endpoints) as slot settings so a swap keeps them in place.',
      'Reference Key Vault secrets with @Microsoft.KeyVault(...) instead of raw values.',
      'Keep this array in source control as the single source of truth for config.',
    ],
    security: [
      'Never commit real secrets; use Key Vault references for anything sensitive.',
      'App settings are encrypted at rest but visible to anyone with portal access — scope RBAC tightly.',
      'Prefer managed identity over connection strings with embedded credentials.',
    ],
  },
  json: [
    { name: 'NODE_ENV', value: 'production', slotSetting: false },
    { name: 'WEBSITE_NODE_DEFAULT_VERSION', value: '~20', slotSetting: false },
    { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1', slotSetting: false },
    {
      name: 'APPLICATIONINSIGHTS_CONNECTION_STRING',
      value: '@Microsoft.KeyVault(SecretUri=https://my-vault.vault.azure.net/secrets/appinsights-conn/)',
      slotSetting: false,
    },
    {
      name: 'DATABASE_URL',
      value: '@Microsoft.KeyVault(SecretUri=https://my-vault.vault.azure.net/secrets/db-url/)',
      slotSetting: true,
    },
    { name: 'API_BASE_URL', value: 'https://api.example.com', slotSetting: true },
  ],
};
