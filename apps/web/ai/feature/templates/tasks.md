# Templates & Knowledge Hub (Frontend) — Task List

**Feature branch:** `templates`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

**Status: ✅ implemented & verified 2026-07-15** — all tasks done. See the "Build note"
in `implementation.md` for as-shipped deviations (zero new deps: TS content modules +
react-markdown; hand-rolled search; localStorage handoff). `npm run build` prerenders
31 static pages; Open-in-Workspace round-trip confirmed live. Deferred: filter→URL sync (task 12's URL part).

---

## A. Content system
| # | Task | Status |
|---|------|--------|
| 1 | Add deps to `package.json` (`gray-matter`, `next-mdx-remote`, `shiki`, `fuse.js`); `npm install --legacy-peer-deps`. | pending |
| 2 | Create `content/templates/` + `content/blog/` with 8–10 seed templates (AWS IAM, S3, OpenAPI, Postman, VS Code, Docker daemon, Firebase, Elasticsearch) and 3–5 seed blog posts. | pending |
| 3 | `lib/templates.ts` — loader + `TemplateMeta`/`Template` types + `getAll*`/`getBySlug`/`getAllSlugs`. | pending |
| 4 | `lib/blog.ts` — loader + `PostMeta` (with `faq[]`) + getters. | pending |
| 5 | `lib/searchIndex.ts` — build-time template index for client search. | pending |
| 6 | `lib/ld.ts` — JSON-LD builders (`techArticleLd`, `breadcrumbLd`, `faqLd`). | pending |

## B. Open in Workspace bridge
| # | Task | Status |
|---|------|--------|
| 7 | `lib/api.ts` — add `seedFromTemplate()` → `POST /api/sessions/from-template`. | pending |
| 8 | `SessionContext.tsx` — hydrate session from a given id + hold `starterPrompts`; use a dedicated `hydrating` flag (NOT global `loading` — avoids the provider-unmount wipe). | pending |
| 9 | `studio/page.tsx` — read `?session=<id>`, hydrate instead of creating a fresh session. | pending |
| 10 | `ChatPanel.tsx` — render `starterPrompts` as clickable chips that prefill/send, clear after first send. | pending |

## C. Pages & components
| # | Task | Status |
|---|------|--------|
| 11 | `components/site/SiteHeader.tsx` — extract nav from `app/page.tsx`; add Templates + Blog links; wire into landing. | pending |
| 12 | `app/templates/page.tsx` + `components/templates/TemplateExplorer` (search + filters + grid + empty state; URL query sync). | pending |
| 13 | `app/templates/[slug]/page.tsx` — `generateStaticParams` + `generateMetadata`; Hero, JsonPreview, AiActionBar, TemplateDocs, RelatedLists. | pending |
| 14 | `components/templates/AiActionBar.tsx` + `TemplateHero.tsx` — Open in Workspace + preset-prompt actions + client Download. | pending |
| 15 | `app/blog/page.tsx` — blog index (cards + tag filter). | pending |
| 16 | `app/blog/[slug]/page.tsx` + `components/blog/*` (AiSummary, CopyButton, InteractiveJson, OpenInWorkspace, Faq); MDX via `next-mdx-remote`. | pending |

## D. SEO
| # | Task | Status |
|---|------|--------|
| 17 | Per-page `generateMetadata` (canonical/OG/Twitter) + `JsonLd` on template + blog detail pages (Breadcrumb + TechArticle/Article + FAQPage). | pending |
| 18 | Extend `app/sitemap.ts` with template + blog URLs; confirm `robots.ts` doesn't block `/templates` or `/blog`. | pending |

## E. Verify
| # | Task | Status |
|---|------|--------|
| 19 | `npm run build` prerenders all pages; run dev server via Browser pane. | pending |
| 20 | Verify: search/filter, detail render, Open in Workspace (POST fires, `/studio?session=` loads JSON + chips), Download, blog copy/FAQ/embeds, nav links, JSON-LD in source, sitemap, 404, anonymous flow. | pending |

---

*Total: 20 tasks. Order: A → B → C → D → E. Depends on backend task 1–7 (`apps/api/ai/feature/templates`) for the `from-template` endpoint. Content authoring (task 2) is an ongoing stream beyond the seed set.*
