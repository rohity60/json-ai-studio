import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'chrome-extension-manifest',
    slug: 'chrome-extension-manifest',
    title: 'Chrome Extension manifest.json (Manifest V3)',
    description:
      'A Manifest V3 manifest.json for a browser extension with a service-worker background script, a toolbar popup, a content script, and narrowly scoped permissions and host_permissions.',
    category: 'Web',
    provider: 'Chrome',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['chrome-extension', 'manifest-v3', 'manifest.json', 'browser', 'mv3'],
    schemaVersion: '3',
    featured: false,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a keyboard shortcut that opens the popup',
      'Replace host_permissions with activeTab',
      'Add an options page',
      'Add a declarativeNetRequest ruleset',
    ],
    relatedTemplates: ['package-json'],
    relatedBlogs: ['chrome-extension-manifest-v3-guide'],
    purpose:
      'Declare what a browser extension is, what code it runs where, and what it is allowed to access.',
    whenToUse:
      'Building or migrating a Chrome (or Chromium-based Edge, Brave, Opera) extension. Manifest V2 extensions no longer run in current Chrome, so new and migrated extensions need V3.',
    requiredFields: [
      'manifest_version: 3',
      'name: the display name',
      'version: one to four dot-separated integers, e.g. "1.2.0"',
    ],
    optionalFields: [
      'background.service_worker: the event-driven background script (replaces MV2 background pages)',
      'action: the toolbar button and its popup (replaces browser_action/page_action)',
      'content_scripts: scripts injected into matching pages',
      'permissions / host_permissions / optional_host_permissions: API and site access',
      'icons / description / options_page / commands',
    ],
    bestPractices: [
      'Prefer activeTab over broad host_permissions; it grants access only when the user clicks.',
      'Move site access the extension does not always need into optional_host_permissions and request it at runtime.',
      'Keep service-worker state in chrome.storage; the worker is stopped when idle.',
      'Use declarativeNetRequest instead of blocking webRequest.',
    ],
    security: [
      'MV3 forbids remotely hosted code; ship every script in the package.',
      'Never use "<all_urls>" unless the extension truly works on every site; it triggers the strongest install warning.',
      'Validate messages from content scripts; web pages can talk to them.',
    ],
    formatSignature: ['/manifest_version', '/name', '/version'],
  },
  json: {
    manifest_version: 3,
    name: 'JSON Peek',
    version: '1.0.0',
    description: 'Pretty-print JSON responses in the current tab.',
    icons: { '16': 'icons/16.png', '48': 'icons/48.png', '128': 'icons/128.png' },
    action: {
      default_popup: 'popup.html',
      default_title: 'JSON Peek',
    },
    background: { service_worker: 'background.js', type: 'module' },
    permissions: ['activeTab', 'storage', 'scripting'],
    optional_host_permissions: ['https://*/*'],
    content_scripts: [
      {
        matches: ['https://api.example.com/*'],
        js: ['content.js'],
        run_at: 'document_idle',
      },
    ],
    commands: {
      _execute_action: {
        suggested_key: { default: 'Ctrl+Shift+J', mac: 'Command+Shift+J' },
      },
    },
  },
};
