import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'azure-functions-host-json',
    slug: 'azure-functions-host-json',
    title: 'Azure Functions host.json',
    description:
      'The global host.json for an Azure Functions app — Application Insights sampling, HTTP route prefix and concurrency, function timeout and retry policy — the runtime-wide behavior knobs.',
    category: 'Cloud',
    provider: 'Azure',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['azure', 'azure-functions', 'serverless', 'host-json', 'logging'],
    schemaVersion: '2.0',
    featured: false,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Set the function timeout to 10 minutes',
      'Disable Application Insights sampling',
      'Add a retry policy with fixed delay',
      'Change the HTTP route prefix to api/v2',
    ],
    relatedTemplates: ['azure-app-service-settings', 'azure-static-web-app-config'],
    relatedBlogs: ['azure-functions-host-json-guide'],
    purpose:
      'Configure runtime-wide behavior for every function in a Functions app — logging, HTTP routing, timeouts, retries and concurrency.',
    whenToUse:
      'Tuning a Functions app for production: controlling Application Insights cost via sampling, capping execution time, or shaping concurrency under load.',
    requiredFields: [
      'version — the host.json schema version, "2.0" for the v2+ runtime',
    ],
    optionalFields: [
      'logging — Application Insights sampling and log level',
      'extensions — per-binding settings such as http.routePrefix',
      'functionTimeout — max duration a single execution may run',
      'retry — the app-wide retry policy',
      'concurrency — dynamic concurrency for scaling',
    ],
    bestPractices: [
      'Keep Application Insights sampling on in production to control telemetry cost.',
      'Set functionTimeout explicitly; the Consumption plan caps it at 10 minutes.',
      'Use a retry policy for transient failures instead of custom try/catch loops.',
    ],
    security: [
      'Do not put secrets in host.json; use application settings or Key Vault references.',
      'Scope the HTTP routePrefix and keep function-level auth keys out of source control.',
      'Lower log verbosity in production to avoid leaking payloads into logs.',
    ],
  },
  json: {
    version: '2.0',
    logging: {
      applicationInsights: {
        samplingSettings: {
          isEnabled: true,
          maxTelemetryItemsPerSecond: 20,
          excludedTypes: 'Request',
        },
      },
      logLevel: {
        default: 'Information',
        'Function.Host': 'Warning',
      },
    },
    extensions: {
      http: {
        routePrefix: 'api',
        maxConcurrentRequests: 100,
        maxOutstandingRequests: 200,
      },
    },
    functionTimeout: '00:05:00',
    retry: {
      strategy: 'fixedDelay',
      maxRetryCount: 3,
      delayInterval: '00:00:05',
    },
    concurrency: {
      dynamicConcurrencyEnabled: true,
      snapshotPersistenceEnabled: true,
    },
  },
};
