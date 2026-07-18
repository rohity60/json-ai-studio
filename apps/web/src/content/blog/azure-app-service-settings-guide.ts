import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'azure-app-service-settings-guide',
    title: 'Managing App Service Settings as JSON',
    description:
      'The bulk-edit JSON format for Azure App Service application settings — what name/value/slotSetting means, when to pin a value to a slot, and how to keep secrets out with Key Vault references.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['azure', 'app-service', 'web-app', 'configuration'],
    readingTime: '5 min',
    aiSummary:
      'App Service settings can be edited in bulk as a JSON array of { name, value, slotSetting }. slotSetting:true pins a value to its deployment slot so a swap keeps it in place. Use @Microsoft.KeyVault(...) references for secrets, and keep the array in source control as the config source of truth.',
    relatedTemplates: ['azure-app-service-settings'],
    relatedBlogs: [],
    faq: [
      {
        q: 'What does slotSetting do?',
        a: 'When true, the setting is "sticky" to its deployment slot. During a slot swap a sticky setting stays put, so production keeps its production database while staging keeps staging.',
      },
      {
        q: 'How do I paste this back into Azure?',
        a: 'In the portal open Configuration → Advanced edit, or use `az webapp config appsettings set --settings @settings.json`.',
      },
    ],
  },
  body: `Editing App Service settings one row at a time in the portal does not scale. The **Advanced edit** blade takes a single JSON array, and so does the CLI — which means your whole environment can live in source control.

## The shape

Every entry is three fields:

\`\`\`json
{ "name": "NODE_ENV", "value": "production", "slotSetting": false }
\`\`\`

- \`name\` — the key, exposed to your app as an environment variable.
- \`value\` — the value.
- \`slotSetting\` — whether the value is pinned to the deployment slot.

## slotSetting: the one that trips people up

Set \`slotSetting: true\` for anything that must **not** follow a slot swap — the database URL, the API base URL, environment-specific endpoints:

\`\`\`json
{ "name": "DATABASE_URL", "value": "...", "slotSetting": true }
\`\`\`

Now swapping staging into production keeps each slot pointed at its own database.

## Keep secrets out

Never paste a raw secret. Reference Key Vault instead — App Service resolves it at runtime:

\`\`\`json
{
  "name": "APPLICATIONINSIGHTS_CONNECTION_STRING",
  "value": "@Microsoft.KeyVault(SecretUri=https://my-vault.vault.azure.net/secrets/appinsights-conn/)",
  "slotSetting": false
}
\`\`\`

## Platform toggles

\`WEBSITE_*\` keys change platform behavior — \`WEBSITE_RUN_FROM_PACKAGE\` for immutable deploys, \`WEBSITE_NODE_DEFAULT_VERSION\` to pin the runtime.

## Security notes

- Settings are encrypted at rest but visible to anyone with portal access — scope RBAC tightly.
- Prefer a managed identity over connection strings that embed credentials.

Open the App Service settings template and ask the workspace to "mark the database connection string as a slot setting" or "add Application Insights connection string", then diff the result.`,
};
