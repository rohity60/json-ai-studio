import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'azure-arm-template',
    slug: 'azure-arm-template',
    title: 'Azure ARM Template — Storage Account',
    description:
      'An Azure Resource Manager (ARM) deployment template that provisions a storage account with parameters, variables and outputs — the canonical ARM structure.',
    category: 'Cloud',
    provider: 'Azure',
    difficulty: 'intermediate',
    estimatedReadTime: '6 min',
    tags: ['azure', 'arm', 'iac', 'storage', 'deployment'],
    schemaVersion: '2019-04-01',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add an output for the resource ID',
      'Add a parameter for the SKU',
      'Output the storage account connection string',
      'Add tags to the resource',
    ],
    relatedTemplates: ['terraform-json', 'gcp-iam-policy'],
    relatedBlogs: [],
    purpose:
      'Declaratively provision Azure resources — here a storage account — with reusable parameters and computed variables.',
    whenToUse:
      'Deploying Azure infrastructure as code via `az deployment group create`, or wiring resources into a CI/CD pipeline.',
    requiredFields: [
      '$schema — the ARM template schema URL',
      'contentVersion — your template version string',
      'resources — the array of resources to deploy',
    ],
    optionalFields: [
      'parameters — inputs supplied at deploy time',
      'variables — values computed from parameters',
      'outputs — values returned after deployment',
    ],
    bestPractices: [
      'Parameterize anything that differs per environment (name, SKU, location).',
      'Use variables to avoid repeating computed expressions.',
      'Pin apiVersion per resource type; do not float it.',
    ],
    security: [
      'Never hardcode secrets; use Key Vault references in parameters.',
      'Set supportsHttpsTrafficOnly to true on storage accounts.',
      'Scope role assignments narrowly in separate templates.',
    ],
  },
  json: {
    $schema:
      'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#',
    contentVersion: '1.0.0.0',
    parameters: {
      storageAccountName: {
        type: 'string',
        metadata: { description: 'Globally unique storage account name' },
      },
      location: {
        type: 'string',
        defaultValue: '[resourceGroup().location]',
      },
    },
    variables: {
      sku: 'Standard_LRS',
    },
    resources: [
      {
        type: 'Microsoft.Storage/storageAccounts',
        apiVersion: '2023-01-01',
        name: "[parameters('storageAccountName')]",
        location: "[parameters('location')]",
        sku: { name: "[variables('sku')]" },
        kind: 'StorageV2',
        properties: {
          supportsHttpsTrafficOnly: true,
          minimumTlsVersion: 'TLS1_2',
        },
      },
    ],
    outputs: {
      storageId: {
        type: 'string',
        value:
          "[resourceId('Microsoft.Storage/storageAccounts', parameters('storageAccountName'))]",
      },
    },
  },
};
