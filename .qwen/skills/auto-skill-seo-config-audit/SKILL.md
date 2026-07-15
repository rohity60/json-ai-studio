---
name: seo-config-audit
description: Audit Next.js App Router SEO config across robots, sitemap, page-level Metadata, OG, Twitter, canonicals, and JSON-LD — catch contradictions like sitemap vs robots disallow
source: auto-skill
extracted_at: '2026-07-15T10:37:00.000Z'
---

## Task: Audit SEO configuration consistency

In a Next.js App Router project, verify that all SEO-related files are aligned. Follow the **four-layer check** below in order — each layer can reveal issues missed by the others.

### Layer 1: `robots.ts` — What crawlers are allowed / blocked?

Read `apps/web/src/app/robots.ts`. Check:

- `rules` entry for `userAgent: '*'` — the **global** allow/disallow rules.
- `rules` entry for `userAgent: AI_BOTS` (or the actual AI bot array name) — the **AI-bots-specific** rules.
- Ensure `/api` is disallowed (should never be crawled).
- Client-only shell routes (e.g. `/studio`) must appear in the AI-bot disallow list — if crawlable content lives elsewhere, these routes have nothing for search engines to index.

### Layer 2: `sitemap.ts` — What URLs do you advertise?

Read `apps/web/src/app/sitemap.ts`. Check:

- **Static routes**: root, `/studio`, `/templates`, `/blog`, etc.
- **Dynamic routes**: `getAllTemplateSlugs()`, `getAllPostSlugs()` — verify these functions exist and actually return slugs.
- Every route in the sitemap must be **crawlable** per `robots.ts`. If a route is disallowed for AI bots in `robots.ts`, **remove it from the sitemap** — contradictory signals hurt indexing.
- For static pages, `lastModified` can be `new Date()` (fine for SSG). Content pages should use the post's actual `updatedAt` if available.

### Layer 3: Page-level `Metadata` — Per-page SEO signals

For each important page file, check:

| File | Required Metadata fields |
|------|------------------------|
| `page.tsx` (landing, `/templates`, `/blog`) | `title`, `description`, `alternates.canonical`, `openGraph.{title, description, url, type}` |
| `[slug]/page.tsx` (template, blog detail) | `generateMetadata()` returning `title`, `description`, `keywords`, `alternates.canonical`, `openGraph.{title, description, url, type: 'article'}`, `twitter.{card, title, description}` |

- `openGraph.url` should be the **relative path** (e.g. `'/templates/slug'`), not the full URL.
- `type` should be `'article'` for blog posts, `'website'` for landing/hub pages, `'website'` for template listings.
- `twitter.card` should be `'summary_large_image'` for article/detail pages.

### Layer 4: JSON-LD — Structured data

Check each page that renders rich content:

| Page | JSON-LD to emit |
|------|----------------|
| Template detail (`[slug]/page.tsx`) | `techArticleLd` or similar — `@type: 'TechArticle'` with author, datePublished, headline |
| Blog post (`[slug]/page.tsx`) | `articleLd` + `faqLd` (if FAQs exist) + `breadcrumbLd` |
| Template listing | Optional — `ItemList` schema if listing many items |
| Root `layout.tsx` | Site-wide `SoftwareApplication` + `Organization` + `WebSite` entity graph |

### Catching contradictions

The most common SEO issues are **conflicting signals** between layers. Here are the patterns to catch:

1. **Sitemap vs robots mismatch**
   - A URL appears in `sitemap.ts` but is disallowed for AI bots in `robots.ts`.
   - **Fix:** Remove the URL from the sitemap. If it's a client-only shell, it has no crawlable content.

2. **Canonical points to wrong page**
   - `alternates.canonical` on a sub-page points to a different route instead of itself.
   - **Fix:** The canonical for `/templates/slug` should be `/templates/slug`, not `/`.

3. **Robots allow index but OG is missing**
   - Page has `robots: { index: true }` but no `openGraph` or `twitter` metadata.
   - **Fix:** Add OG + Twitter cards; social sharing will fall back to bare title/description but look unpolished.

4. **Type mismatch in OG**
   - Blog detail uses `type: 'website'` instead of `'article'`.
   - **Fix:** Use `'article'` for blog posts / long-form content; `'website'` for landing/hub pages.

### Checklist for any new page addition

When adding a new content page, verify:

- [ ] Sitemap includes it (static or dynamic via a `getSlugs()` function)
- [ ] `robots.ts` permits crawling for it (check both `'*'` and AI-bot rules)
- [ ] Page-level `Metadata` object has `title`, `description`, `alternates.canonical`
- [ ] `openGraph` with `title`, `description`, `url`, `type`
- [ ] `twitter` with `card`, `title`, `description`
- [ ] JSON-LD structured data if the page renders rich content
- [ ] No contradictory `noindex` on the page if it should be indexed
