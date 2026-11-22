/** Phase-1 blog catalog (ADR-0019). Add a module + one import line here. */

import type { BlogPost } from '@/content/types';

import { post as whatIsIamPolicy } from './what-is-an-iam-policy';
import { post as iamJsonExplained } from './iam-json-explained';
import { post as leastPrivilegeIam } from './least-privilege-iam';
import { post as commonIamMistakes } from './common-iam-mistakes';
import { post as iamPolicyGenerator } from './iam-policy-generator';
import { post as howAiHelpsIam } from './how-ai-helps-build-iam-policies';
import { post as openapiJsonExplained } from './openapi-json-explained';
import { post as dockerDaemonGuide } from './docker-daemon-json-guide';
import { post as llmThinkingConfig } from './llm-thinking-reasoning-config';
import { post as s3BucketPolicyExplained } from './s3-bucket-policy-explained';
import { post as s3BucketPolicyGenerator } from './s3-bucket-policy-generator';
import { post as s3BucketPolicyVsIam } from './s3-bucket-policy-vs-iam-policy';
import { post as s3StaticWebsiteCloudfront } from './s3-static-website-cloudfront';
import { post as s3SelectAlternatives } from './s3-select-deprecated-alternatives';
// Phase 3 (Azure)
import { post as azureArmVmExplained } from './azure-arm-vm-deployment-explained';
import { post as azureFunctionsHostGuide } from './azure-functions-host-json-guide';
import { post as azureAppServiceSettingsGuide } from './azure-app-service-settings-guide';
import { post as staticwebappConfigGuide } from './staticwebapp-config-json-guide';
// Phase 4 (Dev environments)
import { post as devcontainerGuide } from './devcontainer-json-guide';
// Phase 5 (Dev IDE & AI tooling)
import { post as mcpJsonGuide } from './mcp-json-guide';
import { post as claudeCodeSettingsGuide } from './claude-code-settings-guide';
import { post as continueDevConfigGuide } from './continue-dev-config-guide';
import { post as vscodeLaunchGuide } from './vscode-launch-json-guide';
import { post as vscodeTasksGuide } from './vscode-tasks-json-guide';
// Phase 6 (AV / Room Systems)
import { post as zoomRoomsQsysGuide } from './zoom-rooms-qsys-json-profile';
// Phase 7 (High-demand formats, 2026-11)
import { post as packageJsonGuide } from './package-json-guide';
import { post as tsconfigJsonGuide } from './tsconfig-json-guide';
import { post as jsonSchemaGuide } from './json-schema-guide';
import { post as llmStructuredOutputs } from './llm-structured-outputs-json';
import { post as jsonLdGuide } from './json-ld-structured-data-guide';
import { post as chromeManifestGuide } from './chrome-extension-manifest-v3-guide';
import { post as geojsonGuide } from './geojson-guide';
import { post as dotnetAppsettingsGuide } from './dotnet-appsettings-json-guide';
// Phase 8 (Search-demand gaps, 2026-11)
import { post as sampleJsonDataGuide } from './sample-json-data-guide';
import { post as jsonVsJsonl } from './json-vs-jsonl';
import { post as jsonVsYaml } from './json-vs-yaml';
import { post as jsonVsToon } from './json-vs-toon';
import { post as jsonVsJsonb } from './json-vs-jsonb';
import { post as powerBiThemeGuide } from './power-bi-theme-json-guide';
import { post as gstEInvoiceGuide } from './gst-e-invoice-json-guide';

export const posts: BlogPost[] = [
  whatIsIamPolicy,
  iamJsonExplained,
  leastPrivilegeIam,
  commonIamMistakes,
  iamPolicyGenerator,
  howAiHelpsIam,
  openapiJsonExplained,
  dockerDaemonGuide,
  llmThinkingConfig,
  s3BucketPolicyExplained,
  s3BucketPolicyGenerator,
  s3BucketPolicyVsIam,
  s3StaticWebsiteCloudfront,
  s3SelectAlternatives,
  // Phase 3 (Azure)
  azureArmVmExplained,
  azureFunctionsHostGuide,
  azureAppServiceSettingsGuide,
  staticwebappConfigGuide,
  // Phase 4 (Dev environments)
  devcontainerGuide,
  // Phase 5 (Dev IDE & AI tooling)
  mcpJsonGuide,
  claudeCodeSettingsGuide,
  continueDevConfigGuide,
  vscodeLaunchGuide,
  vscodeTasksGuide,
  // Phase 6 (AV / Room Systems)
  zoomRoomsQsysGuide,
  // Phase 7 (High-demand formats, 2026-11)
  packageJsonGuide,
  tsconfigJsonGuide,
  jsonSchemaGuide,
  llmStructuredOutputs,
  jsonLdGuide,
  chromeManifestGuide,
  geojsonGuide,
  dotnetAppsettingsGuide,
  // Phase 8 (Search-demand gaps, 2026-11)
  sampleJsonDataGuide,
  jsonVsJsonl,
  jsonVsYaml,
  jsonVsToon,
  jsonVsJsonb,
  powerBiThemeGuide,
  gstEInvoiceGuide,
];
