/** Phase-1 template catalog (ADR-0019). Add a module + one import line here. */

import type { Template } from '@/content/types';

// Phase 1
import { template as awsIamReadonly } from './aws-iam-readonly-policy';
import { template as awsS3Bucket } from './aws-s3-bucket-policy';
import { template as awsLambdaS3Event } from './aws-lambda-s3-event';
import { template as openapiSpec } from './openapi-spec';
import { template as postmanCollection } from './postman-collection';
import { template as vscodeSettings } from './vscode-settings';
import { template as dockerDaemon } from './docker-daemon';
import { template as firebaseConfig } from './firebase-config';
import { template as elasticsearchQuery } from './elasticsearch-query';
import { template as mongodbSchema } from './mongodb-schema-validation';
// Phase 2
import { template as azureArm } from './azure-arm-template';
import { template as gcpIam } from './gcp-iam-policy';
import { template as kubernetesDeployment } from './kubernetes-deployment';
import { template as githubActions } from './github-actions-workflow';
import { template as terraformJson } from './terraform-json';
import { template as auth0Client } from './auth0-client-config';
import { template as keycloakRealm } from './keycloak-realm';
import { template as jenkinsPipeline } from './jenkins-pipeline';
import { template as anthropicMessages } from './anthropic-messages-request';
import { template as openaiChat } from './openai-chat-request';
// Phase 3 (Azure)
import { template as azureArmVm } from './azure-arm-vm-deployment';
import { template as azureFunctionsHost } from './azure-functions-host-json';
import { template as azureAppServiceSettings } from './azure-app-service-settings';
import { template as azureStaticWebApp } from './azure-static-web-app-config';
// Phase 4 (Dev environments)
import { template as devcontainer } from './devcontainer-json';
// Phase 5 (Dev IDE & AI tooling)
import { template as mcpServerConfig } from './mcp-server-config';
import { template as claudeCodeSettings } from './claude-code-settings';
import { template as continueDevConfig } from './continue-dev-config';
import { template as vscodeLaunch } from './vscode-launch-json';
import { template as vscodeTasks } from './vscode-tasks-json';

export const templates: Template[] = [
  // Phase 1
  awsIamReadonly,
  awsS3Bucket,
  awsLambdaS3Event,
  openapiSpec,
  postmanCollection,
  vscodeSettings,
  dockerDaemon,
  firebaseConfig,
  elasticsearchQuery,
  mongodbSchema,
  // Phase 2
  azureArm,
  gcpIam,
  kubernetesDeployment,
  githubActions,
  terraformJson,
  auth0Client,
  keycloakRealm,
  jenkinsPipeline,
  anthropicMessages,
  openaiChat,
  // Phase 3 (Azure)
  azureArmVm,
  azureFunctionsHost,
  azureAppServiceSettings,
  azureStaticWebApp,
  // Phase 4 (Dev environments)
  devcontainer,
  // Phase 5 (Dev IDE & AI tooling)
  mcpServerConfig,
  claudeCodeSettings,
  continueDevConfig,
  vscodeLaunch,
  vscodeTasks,
];
