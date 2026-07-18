import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'azure-functions-host-json-guide',
    title: 'The Azure Functions host.json Guide',
    description:
      'What host.json controls across a whole Functions app — Application Insights sampling, HTTP routing and concurrency, function timeout and retry — and the settings that matter most in production.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['azure', 'azure-functions', 'serverless', 'host-json'],
    readingTime: '5 min',
    aiSummary:
      'host.json configures the Functions runtime host-wide. The highest-impact settings are Application Insights sampling (controls telemetry cost), functionTimeout (capped at 10 min on Consumption), the app-wide retry policy, and HTTP concurrency limits. It never holds secrets — those go in application settings.',
    relatedTemplates: ['azure-functions-host-json'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Where does host.json live?',
        a: 'At the root of the Functions app, next to your function folders. It applies to every function in the app.',
      },
      {
        q: 'What is the max functionTimeout?',
        a: 'On the Consumption plan the ceiling is 10 minutes ("00:10:00"). Premium and Dedicated plans allow longer or unbounded execution.',
      },
    ],
  },
  body: `\`host.json\` configures the Azure Functions **runtime host** — not one function, but every function in the app. A handful of settings decide your telemetry bill and your reliability under load.

## Control telemetry cost with sampling

Application Insights bills per ingested item. Sampling caps the rate so a traffic spike does not blow up your bill:

\`\`\`json
"applicationInsights": {
  "samplingSettings": {
    "isEnabled": true,
    "maxTelemetryItemsPerSecond": 20,
    "excludedTypes": "Request"
  }
}
\`\`\`

\`excludedTypes\` keeps every request but samples the noisier traces.

## Cap execution time

\`"functionTimeout": "00:05:00"\` stops runaway executions. On the Consumption plan the hard ceiling is 10 minutes — set it explicitly rather than relying on the default.

## Retry transient failures

An app-wide retry policy beats hand-rolled loops in every function:

\`\`\`json
"retry": {
  "strategy": "fixedDelay",
  "maxRetryCount": 3,
  "delayInterval": "00:00:05"
}
\`\`\`

## Shape HTTP behavior

\`extensions.http\` sets the \`routePrefix\` (default \`api\`) and concurrency limits — \`maxConcurrentRequests\` and \`maxOutstandingRequests\` protect a downstream database from being overwhelmed during a burst.

## Security notes

- host.json is **not** for secrets. Connection strings and keys belong in application settings or Key Vault references.
- Lower \`logLevel\` in production so payloads do not leak into logs.

Open the host.json template and ask the workspace to "set the function timeout to 10 minutes" or "add a retry policy with fixed delay", then diff the result.`,
};
