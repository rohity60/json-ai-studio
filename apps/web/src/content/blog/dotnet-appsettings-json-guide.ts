import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'dotnet-appsettings-json-guide',
    title: 'appsettings.json in ASP.NET Core: Layering, Options and Secrets',
    description:
      'How .NET configuration layers appsettings.json, appsettings.{Environment}.json, user secrets, environment variables and the command line, plus binding sections to options classes and keeping secrets out of the file.',
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    tags: ['dotnet', 'aspnetcore', 'appsettings', 'configuration'],
    readingTime: '6 min',
    aiSummary:
      'appsettings.json is the base layer of ASP.NET Core configuration. Later sources override earlier ones: appsettings.json, then appsettings.{Environment}.json, then user secrets (Development only), then environment variables, then command-line args. Nested keys map to environment variables with a double underscore (Smtp__Port). Bind sections to typed options with AddOptions<T>().Bind(...).ValidateOnStart(). Keep secrets out of the file: use user-secrets locally and Key Vault or environment variables in production.',
    relatedTemplates: ['dotnet-appsettings-json', 'azure-app-service-settings'],
    relatedBlogs: ['azure-app-service-settings-guide'],
    faq: [
      {
        q: 'How do I override a nested appsettings value with an environment variable?',
        a: 'Join the path with a double underscore: Smtp:Port becomes Smtp__Port, and ConnectionStrings:Default becomes ConnectionStrings__Default. On Azure App Service, app settings use the same naming.',
      },
      {
        q: 'Which appsettings file is used in production?',
        a: 'appsettings.json is always loaded, then appsettings.{Environment}.json for the current ASPNETCORE_ENVIRONMENT (or DOTNET_ENVIRONMENT). It defaults to Production when unset, so appsettings.Production.json applies.',
      },
      {
        q: 'Can appsettings.json have comments?',
        a: 'Yes. The .NET JSON configuration provider accepts comments and trailing commas, but keep the file valid JSON if other tools read it too.',
      },
    ],
  },
  body: `\`appsettings.json\` is where an ASP.NET Core app keeps its settings. It is only the **first layer**, though. Understanding the layering is most of the job.

## The layering order

Each source overrides the ones before it:

1. \`appsettings.json\`
2. \`appsettings.{Environment}.json\`, such as \`appsettings.Development.json\`
3. User secrets (Development environment only)
4. Environment variables
5. Command-line arguments

So defaults go in \`appsettings.json\`, per-environment tweaks go in the environment file, and secrets come from 3–5 or a vault. Secrets never go in the committed file.

## The usual sections

\`\`\`json
{
  "Logging": { "LogLevel": { "Default": "Information", "Microsoft.AspNetCore": "Warning" } },
  "AllowedHosts": "example.com;*.example.com",
  "ConnectionStrings": { "Default": "Host=localhost;Database=app;Username=app" }
}
\`\`\`

- **Logging.LogLevel**: minimum level per category. Use the most specific category name you can.
- **AllowedHosts**: host-header filtering. \`"*"\` allows any host.
- **ConnectionStrings**: read with \`builder.Configuration.GetConnectionString("Default")\`.

## Environment variables for nested keys

The \`:\` path separator becomes \`__\`:

\`\`\`bash
export ConnectionStrings__Default="Host=db;Database=app;Username=app;Password=..."
export Smtp__Port=2525
\`\`\`

This works the same way in Docker, Kubernetes and Azure App Service settings.

## Typed options instead of string lookups

\`\`\`json
"Smtp": { "Host": "smtp.example.com", "Port": 587, "UseStartTls": true }
\`\`\`

\`\`\`csharp
builder.Services.AddOptions<SmtpOptions>()
    .Bind(builder.Configuration.GetSection("Smtp"))
    .ValidateDataAnnotations()
    .ValidateOnStart();
\`\`\`

\`ValidateOnStart()\` makes a missing or invalid value fail at boot, not on the first email.

## Kestrel endpoints

\`\`\`json
"Kestrel": { "Endpoints": { "Http": { "Url": "http://0.0.0.0:8080" } } }
\`\`\`

Containers typically listen on 8080 over plain HTTP and let the ingress terminate TLS.

## Security notes

- Locally, run \`dotnet user-secrets set "ConnectionStrings:Default" "..."\`. It stores values outside the repo.
- In production, use environment variables, Key Vault references or a managed identity, never a committed password.
- Avoid \`Debug\` log levels in production. They can log request data.

Open the appsettings template and ask the workspace to "add a Redis connection string" or "lower Microsoft.AspNetCore logging to Warning", then review the diff.`,
};
