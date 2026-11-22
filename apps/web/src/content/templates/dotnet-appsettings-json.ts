import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'dotnet-appsettings-json',
    slug: 'dotnet-appsettings-json',
    title: '.NET appsettings.json',
    description:
      'An ASP.NET Core appsettings.json with logging levels, connection strings, AllowedHosts, Kestrel endpoints and a strongly typed options section. It is the base layer of .NET configuration.',
    category: 'Backend',
    provider: '.NET',
    difficulty: 'beginner',
    estimatedReadTime: '5 min',
    tags: ['dotnet', 'aspnetcore', 'appsettings', 'configuration', 'csharp'],
    schemaVersion: '.NET 10',
    featured: false,
    updatedAt: '2026-11-21',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a Serilog section that writes to the console',
      'Add a Redis connection string',
      'Lower Microsoft.AspNetCore logging to Warning',
      'Add an HTTPS endpoint to Kestrel',
    ],
    relatedTemplates: ['azure-app-service-settings', 'docker-daemon'],
    relatedBlogs: ['dotnet-appsettings-json-guide', 'azure-app-service-settings-guide'],
    purpose:
      'Hold an ASP.NET Core app\'s non-secret settings, which the configuration system layers with environment-specific files, environment variables and secret stores.',
    whenToUse:
      'Any ASP.NET Core or .NET worker app. Put defaults here, overrides in appsettings.{Environment}.json, and secrets in user-secrets, environment variables or Key Vault.',
    requiredFields: [
      'None: the file is optional, but Logging and AllowedHosts are in every template',
    ],
    optionalFields: [
      'Logging.LogLevel: minimum levels per category ("Default", "Microsoft.AspNetCore")',
      'ConnectionStrings: read with GetConnectionString("Name")',
      'AllowedHosts: host filtering, e.g. "example.com;*.example.com"',
      'Kestrel.Endpoints: listen URLs and certificates',
      'Custom sections: bound to a class with services.Configure<T>(...) or AddOptions<T>().Bind(...)',
    ],
    bestPractices: [
      'Later sources win: appsettings.json < appsettings.{Environment}.json < user secrets (Development) < environment variables < command line.',
      'Override nested keys from environment variables with a double underscore: Smtp__Port=2525.',
      'Bind sections to options classes with ValidateOnStart() so bad config fails at boot.',
    ],
    security: [
      'Do not commit real passwords in ConnectionStrings; use user-secrets locally and Key Vault or environment variables in production.',
      'Avoid AllowedHosts "*" in production behind a public endpoint.',
      'Keep Logging at Information or above in production; Debug can log request data.',
    ],
    formatSignature: ['/Logging/LogLevel'],
  },
  json: {
    Logging: {
      LogLevel: {
        Default: 'Information',
        'Microsoft.AspNetCore': 'Warning',
      },
    },
    AllowedHosts: 'example.com;*.example.com',
    ConnectionStrings: {
      Default: 'Host=localhost;Port=5432;Database=app;Username=app',
    },
    Kestrel: {
      Endpoints: {
        Http: { Url: 'http://0.0.0.0:8080' },
      },
    },
    Smtp: {
      Host: 'smtp.example.com',
      Port: 587,
      UseStartTls: true,
      From: 'noreply@example.com',
    },
    FeatureFlags: {
      NewCheckout: false,
    },
  },
};
