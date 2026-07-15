# 0019-static-git-content-for-templates-and-blog-hub

**Date**: 2026-07-15
**Status**: Accepted

## Context

The Templates & Knowledge Hub (PRD `docs/prd/templates.prd`) adds a public library of configuration templates (AWS IAM, OpenAPI, Docker daemon, VS Code settings, …) and a blog CMS. Its primary goals are **organic SEO traffic** and **funnelling visitors into the AI Workspace** — not durable user data. Each template carries structured metadata (id, slug, title, category, provider, difficulty, tags, docs sections, the JSON itself) and links to related templates/blogs.

The app already has Postgres (ADR-0015) and a workspaces persistence layer (ADR-0018). The open question: does template/blog content live in the **database behind a `/api/templates` CMS**, or as **static files in the git repo, statically generated (SSG)**?

The PRD's own architecture diagram leans static: *Content Repository → Markdown + JSON metadata → Static Site Generation → Template Detail Pages*.

## Decision

**Template and blog content lives as static MDX + frontmatter files in the web repo (`apps/web/content/{templates,blog}/`), rendered by Next.js SSG. There is no templates/blog database and no content API.** The FastAPI backend gains exactly one endpoint for this feature — session seeding (ADR-0020) — and stores nothing about the catalog.

### What this means

- **Content = files.** `content/templates/<slug>.mdx` (YAML frontmatter for metadata + docs, JSON in a fenced block or sibling `<slug>.json`) and `content/blog/<slug>.mdx`. Build-time loaders (`lib/templates.ts`, `lib/blog.ts`, `gray-matter`) parse them; `generateStaticParams` prerenders every page.
- **Search & filter are client-side** over a build-time index (`lib/searchIndex.ts`) — no query endpoint. At MVP scale (tens to low-hundreds of templates) an in-browser filter over a JSON index is instant and needs zero infra.
- **SEO is first-class.** Every page is a prerendered static route with per-page `generateMetadata` (canonical/OG/Twitter), JSON-LD (`TechArticle`/`Article`/`FAQPage`/`BreadcrumbList`), and sitemap entries enumerated from the loaders. Static HTML is what crawlers reward.
- **Authoring = a PR.** Adding a template or article is a new file + rebuild, versioned in git, reviewable, no admin UI or migration.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Postgres `templates`/`posts` tables + `GET /api/templates` CMS | Heavy infra for read-mostly public content; SSR/DB round-trip per page hurts SEO and TTFB; needs an admin UI, migrations, and a cache layer to match what SSG gives free. No user-write requirement at MVP. |
| Hybrid (static content + DB for search/popularity) | Adds a backend dependency for a search that a client-side index already serves instantly at this scale. Deferred until a real popularity/counter requirement lands (Phase 3). |
| Headless CMS (Contentful/Sanity) | External dependency, cost, and network calls for content the team authors in-repo anyway; git-as-CMS keeps content and code in one reviewable history. |

## Consequences

- **The good:** Fastest possible pages (static HTML/CDN), strong SEO, zero new backend surface for the catalog, content changes are ordinary reviewed PRs, works with no DB configured. Aligns with the PRD diagram.
- **The bad:** Every content change requires a rebuild/redeploy — no live editing. Non-technical authoring needs MDX familiarity (or a later import tool). Content scale is bounded by build time; fine for hundreds, revisit for tens of thousands.
- **Neutral:** Popularity indicators, ratings, and community submissions (PRD Phase 3) are explicitly out — they *would* need a backend and can revisit this decision then. The full 50–75 template catalog is a content backlog, independent of this code.
- New deps in `apps/web`: `gray-matter`, `next-mdx-remote`, `shiki`, `fuse.js` (install `--legacy-peer-deps`, React 19).

## References

- PRD: `docs/prd/templates.prd` (§13 Content Strategy, §14 Technical Architecture)
- Feature docs: `apps/web/ai/feature/templates/{requirements,implementation,tasks}.md`
- Related: ADR-0020 (session seeding endpoint), ADR-0018 (workspaces persistence), ADR-0011/0012 (contract-first), ADR-0008 (JSON tree rendering, reused for preview)
