/** Template content loader (ADR-0019). Static, build-time; no backend. */

import { templates } from '@/content/templates';
import type { Template, TemplateMeta } from '@/content/types';

export function getAllTemplates(): Template[] {
  return [...templates].sort((a, b) => a.meta.title.localeCompare(b.meta.title));
}

export function getAllTemplateSlugs(): string[] {
  return templates.map((t) => t.meta.slug);
}

export function getTemplateBySlug(slug: string): Template | undefined {
  return templates.find((t) => t.meta.slug === slug);
}

export function getFeaturedTemplates(): Template[] {
  return getAllTemplates().filter((t) => t.meta.featured);
}

export function getRelatedTemplates(slugs: string[]): TemplateMeta[] {
  return slugs
    .map((s) => getTemplateBySlug(s)?.meta)
    .filter((m): m is TemplateMeta => Boolean(m));
}

/** Distinct facet values for filter UIs. */
export function getTemplateFacets() {
  const all = getAllTemplates();
  const uniq = (xs: string[]) => Array.from(new Set(xs)).sort();
  return {
    categories: uniq(all.map((t) => t.meta.category)),
    providers: uniq(all.map((t) => t.meta.provider)),
    difficulties: uniq(all.map((t) => t.meta.difficulty)),
    tags: uniq(all.flatMap((t) => t.meta.tags)),
  };
}

/** Lightweight index passed to the client explorer for in-browser search. */
export interface TemplateIndexItem {
  slug: string;
  title: string;
  description: string;
  category: string;
  provider: string;
  difficulty: string;
  tags: string[];
  featured: boolean;
}

export function buildTemplateIndex(): TemplateIndexItem[] {
  return getAllTemplates().map((t) => ({
    slug: t.meta.slug,
    title: t.meta.title,
    description: t.meta.description,
    category: t.meta.category,
    provider: t.meta.provider,
    difficulty: t.meta.difficulty,
    tags: t.meta.tags,
    featured: t.meta.featured,
  }));
}
