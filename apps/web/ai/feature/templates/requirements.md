# Frontend Requirements — AI Configuration Templates & Knowledge Hub

Derived from PRD `docs/prd/templates.prd`. Only what the **client / web layer** must implement.

**Scope decisions (from PRD review):**
- Covers the **Template library + Template detail pages + Blog CMS** (PRD §4–§12). Community contributions / ratings (Phase 3) and future enhancements are out.
- Content lives as **static files in git**, statically generated (SSG). No template/blog backend.
- "Open in Workspace" calls the new backend endpoint `POST /api/sessions/from-template`, then routes to `/studio`.

Feature branch: `templates`.

---

## 1. Content Model

| # | Requirement | Priority |
|---|-------------|----------|
| CM-01 | Templates stored under `apps/web/content/templates/<slug>.mdx` — YAML frontmatter (metadata + docs) + the template JSON in a fenced block or a sibling `<slug>.json`. | MVP |
| CM-02 | Frontmatter fields (PRD §9): `id, slug, title, description, category, provider, difficulty, estimated_read_time, tags[], schema_version, featured, updated_at, author`, plus `starter_prompts[]`, `related_templates[]` (slugs), `related_blogs[]` (slugs), and doc sections `purpose, when_to_use, required_fields[], optional_fields[], best_practices[], security[]`. | MVP |
| CM-03 | Blog articles under `apps/web/content/blog/<slug>.mdx` — frontmatter: `slug, title, description, updated_at, author, tags[], related_templates[], related_blogs[], faq[] ({q,a}), reading_time`. Body is MDX. | MVP |
| CM-04 | Content loaders `lib/templates.ts` + `lib/blog.ts`: read + parse files at build (`gray-matter`), expose `getAll*`, `get*BySlug`, `getAllSlugs`. Typed via TS interfaces (hand-written, mirror frontmatter). | MVP |
| CM-05 | A build-time **search index** (`lib/searchIndex.ts` or generated JSON) of `{slug, title, description, category, provider, difficulty, tags}` for client-side search — no runtime backend. | MVP |
| CM-06 | Seed content for launch: **8–10 templates** across categories (AWS IAM, S3 policy, OpenAPI, Postman, VS Code settings, Docker daemon, Firebase, Elasticsearch query) + **3–5 blog articles**. Enough to prove the system; not the full 50–75 (that's a content task, not code). | MVP |

---

## 2. Routing & Pages

| # | Requirement | Priority |
|---|-------------|----------|
| R-01 | `/templates` — library index: search bar, filters (category, provider, difficulty, tags), responsive card grid, featured section. Statically generated. | MVP |
| R-02 | `/templates/[slug]` — detail page. `generateStaticParams` over all slugs. `generateMetadata` per template. | MVP |
| R-03 | `/blog` — blog index: article cards, tag filter. | MVP |
| R-04 | `/blog/[slug]` — article page. `generateStaticParams` + `generateMetadata`. | MVP |
| R-05 | Unknown slug → `notFound()` (Next 404). | MVP |

### 2.1 Template Detail Sections (PRD §5)
| # | Requirement | Priority |
|---|-------------|----------|
| TD-01 | **Hero:** title, description, tags, difficulty badge, **"Open in AI Workspace"** primary button. | MVP |
| TD-02 | **Preview:** syntax-highlighted JSON (read-only). Reuse `JSONTree` or a highlighter; must not depend on a running backend. | MVP |
| TD-03 | **AI Actions bar:** buttons `Explain, Customize, Validate, Improve, Fix, Download`. `Download` = client-side JSON blob download. The other five open the workspace with a preset starter prompt (see §4). | MVP |
| TD-04 | **Documentation:** Purpose, When to use, Required fields, Optional fields, Best practices, Security considerations (from frontmatter). | MVP |
| TD-05 | **Related Templates** + **Related Blogs** link lists (from frontmatter slugs). | MVP |

### 2.2 Blog Article Sections (PRD §11)
| # | Requirement | Priority |
|---|-------------|----------|
| BL-01 | MDX body with code snippets + **copy button** on each code block. | MVP |
| BL-02 | **Interactive JSON** embeds (reuse `JSONTree`) and **"Open in Workspace"** buttons inside articles. | MVP |
| BL-03 | Related Templates + Related Blogs lists. | MVP |
| BL-04 | **FAQ** section rendered from `faq[]` frontmatter (also feeds FAQ JSON-LD). | MVP |
| BL-05 | **AI Summary** block at the top (static text authored in frontmatter/MDX; no live LLM call at build). | MVP |

---

## 3. Navigation & Search

| # | Requirement | Priority |
|---|-------------|----------|
| N-01 | Add **Templates** and **Blog** to the top nav (target order: Home, Workspace, Templates, Blog, Pricing, GitHub — Pricing may be a stub link). Nav currently lives inline in `app/page.tsx`; extract a shared `SiteHeader` used by landing + templates + blog. | MVP |
| N-02 | Search bar on `/templates`: filters the card grid client-side (title/description/tags/provider) using the build-time index. Debounced, no backend. | MVP |
| N-03 | Filters: category, provider, difficulty, tags — combinable, reflected in URL query (`?category=cloud&difficulty=beginner`) for shareable/SEO-friendly filtered views. | MVP |
| N-04 | Empty-state when no results. | MVP |

---

## 4. Open in Workspace

| # | Requirement | Priority |
|---|-------------|----------|
| OW-01 | `api.ts` gains `seedFromTemplate(slug, title, json, starterPrompts)` → `POST /api/sessions/from-template`, returns `{ sessionId, working_json, starter_prompts }`. | MVP |
| OW-02 | "Open in AI Workspace" (and AI-action buttons) call it, then `router.push('/studio?session=<id>')`. On failure → toast + stay on template page. | MVP |
| OW-03 | AI-action buttons pass a **preset starter prompt** as the first entry of `starterPrompts` (Explain→"Explain each field", Customize→"", Validate→"Validate this against best practices", Improve→"Suggest improvements", Fix→"Find and fix problems"). Combined with the template's own `starter_prompts`. | MVP |
| OW-04 | `/studio` reads `?session=<id>`: if present, loads that session (via existing session-fetch path) instead of creating a fresh one, and renders `starter_prompts` as clickable chips in the chat input that prefill/send on click. | MVP |
| OW-05 | Anonymous users can Open in Workspace (uses the browser `X-API-Key`, same as today). No login gate. | MVP |

---

## 5. SEO (PRD §12)

| # | Requirement | Priority |
|---|-------------|----------|
| SEO-01 | `generateMetadata` per template/blog page: title, description, canonical URL, OpenGraph, Twitter card. | MVP |
| SEO-02 | Extend `app/sitemap.ts` to enumerate all `/templates/<slug>` and `/blog/<slug>` from the content loaders. | MVP |
| SEO-03 | JSON-LD via existing `JsonLd` component: `TechArticle`/`HowTo` for templates, `Article` + `FAQPage` (from `faq[]`) for blogs, `BreadcrumbList` on both. | MVP |
| SEO-04 | Breadcrumbs UI (Home / Templates / <title>) on detail pages, matching the JSON-LD. | MVP |
| SEO-05 | Ensure `/templates` and `/blog` trees are not blocked by `robots.ts` (they should be crawlable). | MVP |

---

## 6. Excluded from MVP (frontend)

- Community submissions, ratings, comments, verified badges (Phase 3).
- "Used by X developers" / popularity indicators (needs backend counter).
- Live AI-generated template creation from NL.
- Convert-to-YAML/TOML/XML on the template page (§10 Convert) — link to workspace instead.
- Field-level "click a field → explain" on the static preview (opens workspace Explain instead).
- Full 50–75 template catalog (content backlog, tracked separately).
- Authenticated template favoriting / history.

---

*End of frontend requirements. Feature branch: `templates`. Content-heavy: code delivers the system; templates/blogs are an ongoing content stream.*
