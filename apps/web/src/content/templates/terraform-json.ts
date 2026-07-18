import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'terraform-json',
    slug: 'terraform-json',
    title: 'Terraform Configuration (JSON syntax)',
    description:
      'A Terraform config in the native JSON syntax (.tf.json) — provider, variable, resource and output — for tooling that generates Terraform programmatically.',
    category: 'DevOps',
    provider: 'Terraform',
    difficulty: 'advanced',
    estimatedReadTime: '6 min',
    tags: ['terraform', 'iac', 'devops', 'hcl', 'aws'],
    schemaVersion: '1.0',
    featured: false,
    updatedAt: '2026-07-15',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a tag block to the resource',
      'Add an S3 bucket resource',
      'Parameterize the region as a variable',
      'Add an output for the instance public IP',
    ],
    relatedTemplates: ['azure-arm-template', 'aws-s3-bucket-policy'],
    relatedBlogs: [],
    purpose:
      'Describe infrastructure declaratively in Terraform’s JSON syntax, equivalent to HCL but machine-generatable.',
    whenToUse:
      'When a tool emits or consumes Terraform config as JSON (.tf.json) rather than hand-written HCL.',
    requiredFields: [
      'resource — the infrastructure to manage',
      'provider — the target platform and its config',
    ],
    optionalFields: [
      'variable — typed inputs with optional defaults',
      'output — values exposed after apply',
      'terraform.required_providers — provider version pins',
    ],
    bestPractices: [
      'Pin provider versions under required_providers.',
      'Keep state in a remote backend, never local for teams.',
      'Use variables and outputs instead of hardcoding values.',
    ],
    security: [
      'Never commit .tfstate — it can contain secrets in plaintext.',
      'Pass credentials via environment or a secrets manager, not the config.',
      'Review `terraform plan` before every apply.',
    ],
  },
  json: {
    terraform: {
      required_providers: {
        aws: { source: 'hashicorp/aws', version: '~> 5.0' },
      },
    },
    provider: { aws: { region: '${var.region}' } },
    variable: {
      region: { type: 'string', default: 'us-east-1' },
    },
    resource: {
      aws_instance: {
        web: {
          ami: 'ami-0c55b159cbfafe1f0',
          instance_type: 't3.micro',
          tags: { Name: 'web' },
        },
      },
    },
    output: {
      public_ip: { value: '${aws_instance.web.public_ip}' },
    },
  },
};
