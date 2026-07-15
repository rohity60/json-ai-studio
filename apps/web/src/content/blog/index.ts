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
];
