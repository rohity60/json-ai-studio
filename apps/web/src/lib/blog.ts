/** Blog content loader (ADR-0019). Static, build-time; no backend. */

import { posts } from '@/content/blog';
import type { BlogMeta, BlogPost } from '@/content/types';

export function getAllPosts(): BlogPost[] {
  return [...posts].sort(
    (a, b) => +new Date(b.meta.updatedAt) - +new Date(a.meta.updatedAt),
  );
}

export function getAllPostSlugs(): string[] {
  return posts.map((p) => p.meta.slug);
}

export function getPostBySlug(slug: string): BlogPost | undefined {
  return posts.find((p) => p.meta.slug === slug);
}

export function getRelatedPosts(slugs: string[]): BlogMeta[] {
  return slugs
    .map((s) => getPostBySlug(s)?.meta)
    .filter((m): m is BlogMeta => Boolean(m));
}

export function getAllBlogTags(): string[] {
  return Array.from(new Set(posts.flatMap((p) => p.meta.tags))).sort();
}
