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
];
