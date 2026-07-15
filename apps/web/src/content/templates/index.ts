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
];
