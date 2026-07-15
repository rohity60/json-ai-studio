/** Static content model for the Templates & Knowledge Hub (ADR-0019).
 *
 *  Content is authored as typed TS modules (not MDX/DB) so it is fully
 *  type-checked and works in every Next rendering mode with zero new deps.
 */

export type Difficulty = 'beginner' | 'intermediate' | 'advanced';

export interface TemplateMeta {
  id: string;
  slug: string;
  title: string;
  description: string;
  category: string; // e.g. "Cloud", "DevOps", "APIs", "IDE", "Databases"
  provider: string; // e.g. "AWS", "Docker", "OpenAPI"
  difficulty: Difficulty;
  estimatedReadTime: string; // "4 min"
  tags: string[];
  schemaVersion: string;
  featured: boolean;
  updatedAt: string; // ISO date
  author: string;
  starterPrompts: string[]; // chips shown in the studio when opened
  relatedTemplates: string[]; // slugs
  relatedBlogs: string[]; // slugs
  // Documentation sections (PRD §5)
  purpose: string;
  whenToUse: string;
  requiredFields: string[];
  optionalFields: string[];
  bestPractices: string[];
  security: string[];
}

export interface Template {
  meta: TemplateMeta;
  json: unknown; // the template payload seeded into the workspace
}

export interface FaqItem {
  q: string;
  a: string;
}

export interface BlogMeta {
  slug: string;
  title: string;
  description: string;
  updatedAt: string;
  author: string;
  tags: string[];
  readingTime: string;
  aiSummary: string; // static AI summary block (authored, no live LLM)
  relatedTemplates: string[]; // slugs
  relatedBlogs: string[]; // slugs
  faq: FaqItem[];
}

export interface BlogPost {
  meta: BlogMeta;
  body: string; // Markdown, rendered with react-markdown
}
