import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'chrome-extension-manifest-v3-guide',
    title: 'Chrome Extension manifest.json: A Manifest V3 Guide (and V2 Migration)',
    description:
      'How a Manifest V3 manifest.json works: service-worker background scripts, action popups, content scripts, permissions vs host_permissions, and a V2-to-V3 migration table.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['chrome-extension', 'manifest-v3', 'manifest.json', 'browser'],
    readingTime: '7 min',
    aiSummary:
      'Every Chrome extension starts with manifest.json, and current Chrome only runs Manifest V3. It requires manifest_version 3, name and version. background.service_worker replaces persistent background pages and is stopped when idle, so state belongs in chrome.storage. action replaces browser_action/page_action. Site access lives in host_permissions, separate from API permissions. Prefer activeTab and optional_host_permissions over broad access, use declarativeNetRequest instead of blocking webRequest, and ship all code in the package because remote code is forbidden.',
    relatedTemplates: ['chrome-extension-manifest', 'package-json'],
    relatedBlogs: ['package-json-guide'],
    faq: [
      {
        q: 'Do Manifest V2 extensions still work?',
        a: 'Not in current Chrome. Chrome phased out Manifest V2 across 2024–2025, and V2 extensions are disabled in current stable releases. New and updated extensions must use Manifest V3.',
      },
      {
        q: 'Why does my service worker lose its variables?',
        a: 'Chrome stops MV3 service workers when idle and restarts them on the next event, which resets globals. Keep state in chrome.storage (session or local), and register event listeners at the top level of the script, not inside async callbacks.',
      },
      {
        q: 'permissions vs host_permissions?',
        a: 'permissions lists extension APIs (storage, scripting, alarms). host_permissions lists the sites the extension can read or modify ("https://api.example.com/*"). Sites in optional_host_permissions can be requested at runtime, which reduces the install warning.',
      },
    ],
  },
  body: `\`manifest.json\` is the root of every browser extension. It declares what the extension is called, what code runs where and what it can access. Chrome, Edge, Brave and Opera all run **Manifest V3** now.

## The required three

\`\`\`json
{ "manifest_version": 3, "name": "JSON Peek", "version": "1.0.0" }
\`\`\`

\`version\` is one to four dot-separated integers. It is not full semver, so \`1.0.0-beta\` is rejected.

## Background: a service worker, not a page

\`\`\`json
"background": { "service_worker": "background.js", "type": "module" }
\`\`\`

MV3 replaced always-on background pages with an **event-driven service worker**. Chrome stops it when idle, so:

- keep state in \`chrome.storage\`, not global variables;
- register listeners (\`chrome.runtime.onMessage\`, \`chrome.alarms.onAlarm\`) at the top level;
- use \`chrome.alarms\` instead of long \`setTimeout\` timers.

## The toolbar button: action

\`\`\`json
"action": { "default_popup": "popup.html", "default_title": "JSON Peek" }
\`\`\`

\`action\` replaces MV2's \`browser_action\` and \`page_action\`.

## Content scripts

\`\`\`json
"content_scripts": [
  { "matches": ["https://api.example.com/*"], "js": ["content.js"], "run_at": "document_idle" }
]
\`\`\`

Content scripts run inside matching pages, in an isolated world. To inject only on demand, use \`chrome.scripting.executeScript\` with the \`scripting\` permission instead.

## Permissions without scary warnings

\`\`\`json
"permissions": ["activeTab", "storage", "scripting"],
"optional_host_permissions": ["https://*/*"]
\`\`\`

- **activeTab** grants temporary access to the current tab only when the user clicks your action. No install warning.
- **host_permissions** grants standing access to sites. Every pattern adds to the warning, and \`<all_urls>\` triggers the strongest one.
- **optional_host_permissions** lets you ask at runtime, when the user needs the feature.

## Migrating from V2

| Manifest V2 | Manifest V3 |
|---|---|
| \`"background": { "scripts": [...] }\` | \`"background": { "service_worker": "..." }\` |
| \`browser_action\` / \`page_action\` | \`action\` |
| hosts inside \`permissions\` | \`host_permissions\` |
| blocking \`webRequest\` | \`declarativeNetRequest\` |
| \`chrome.tabs.executeScript\` | \`chrome.scripting.executeScript\` |
| remotely hosted code | forbidden: bundle everything |
| \`web_accessible_resources: [...]\` | objects with \`resources\` + \`matches\` |

## Security notes

- MV3 forbids remote code. Every script ships in the package and is reviewed with it.
- Treat messages from content scripts as untrusted. A malicious page can talk to your content script.
- Request the narrowest host patterns you can, and drop permissions you no longer use.

Open the Manifest V3 template and ask the workspace to "replace host_permissions with activeTab" or "add an options page", then review the diff.`,
};
