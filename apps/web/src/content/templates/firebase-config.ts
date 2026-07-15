import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'firebase-config',
    slug: 'firebase-config',
    title: 'Firebase Project Config (firebase.json)',
    description:
      'A firebase.json wiring up Hosting with SPA rewrites and cache headers, plus Firestore and emulator settings — a typical web-app deploy config.',
    category: 'Authentication',
    provider: 'Firebase',
    difficulty: 'intermediate',
    estimatedReadTime: '5 min',
    tags: ['firebase', 'hosting', 'firestore', 'config', 'deploy'],
    schemaVersion: '1.0',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Explain each section of this config',
      'Add a redirect from /old to /new',
      'Cache images for 30 days',
      'Add Cloud Functions configuration',
    ],
    relatedTemplates: [],
    relatedBlogs: [],
    purpose:
      'Describe how the Firebase CLI deploys a project — hosting rewrites, headers, Firestore rules, and local emulators.',
    whenToUse:
      'Deploying a single-page app to Firebase Hosting with Firestore, and running the local emulator suite during development.',
    requiredFields: [
      'No single field is required — you include only the products you use (hosting, firestore, functions…).',
    ],
    optionalFields: [
      'hosting.rewrites — SPA fallback to index.html',
      'hosting.headers — cache-control and security headers',
      'firestore.rules / indexes — database config files',
      'emulators — local ports for the emulator suite',
    ],
    bestPractices: [
      'Use a catch-all rewrite to index.html for client-side routing.',
      'Set long cache lifetimes on hashed static assets, short on HTML.',
      'Keep security rules in a separate firestore.rules file, referenced here.',
    ],
    security: [
      'firebase.json is safe to commit — it holds no secrets or API keys.',
      'Your real security boundary is firestore.rules, not this file.',
    ],
  },
  json: {
    hosting: {
      public: 'dist',
      ignore: ['firebase.json', '**/.*', '**/node_modules/**'],
      rewrites: [{ source: '**', destination: '/index.html' }],
      headers: [
        {
          source: '**/*.@(js|css|woff2)',
          headers: [{ key: 'Cache-Control', value: 'max-age=31536000, immutable' }],
        },
      ],
    },
    firestore: { rules: 'firestore.rules', indexes: 'firestore.indexes.json' },
    emulators: {
      auth: { port: 9099 },
      firestore: { port: 8080 },
      hosting: { port: 5000 },
      ui: { enabled: true },
    },
  },
};
