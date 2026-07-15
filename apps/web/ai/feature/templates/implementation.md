# Frontend Implementation Guide — Templates & Knowledge Hub

**Feature branch:** `templates`
**Requirements:** `requirements.md`

> **Build note (2026-07-15) — as-shipped deviations from the plan below.**
> Implemented to de-risk the build. All requirements still met.
> - **Zero new dependencies.** No `gray-matter`/`next-mdx-remote`/`shiki`/`fuse.js`.
>   Content is authored as **typed TS modules** under `src/content/{templates,blog}/`
>   (`*.ts` exporting a typed object, aggregated by an `index.ts`). Loaders
>   (`lib/templates.ts`, `lib/blog.ts`) re-export + provide getters.
> - **Blog bodies** render with the already-installed `react-markdown` (explicit
>   `components` map — no typography plugin). `components/blog/PostBody.tsx`.
> - **JSON preview** is a read-only, crawlable `<pre>` (`components/templates/JsonPreview.tsx`),
>   not shiki. Search/filter is a hand-rolled client filter (`TemplateExplorer`), not fuse.
> - **Open-in-Workspace handoff** reuses the existing `localStorage` session-restore
>   path (writes `json-ai-studio-session`, stashes prompts in `sessionStorage`) →
>   `router.push('/studio')`. No changes to the fragile hydrate effect. See
>   `lib/openInWorkspace.ts` (`useOpenInWorkspace`, `peekStarterPrompts`,
>   `clearStarterPrompts`). Starter-prompt read is **non-destructive** (peek, not
>   take) so React StrictMode's double-invoked mount effect doesn't wipe them;
>   cleared on first send.
> - **Nav:** `components/site/SiteHeader.tsx` used on hub pages; landing keeps its
>   own header, with Templates/Blog links added inline.
> - **Deferred:** filter→URL query sync (N-03) — client-state filters only for now.
> - **Content shipped:** 10 Phase-1 templates + 8 blog posts (full IAM cluster +
>   OpenAPI/Docker explainers).
> - **Verified:** `npm run build` prerenders 31 static pages; Open-in-Workspace
>   round-trip confirmed live (POST → 201 → studio loads seeded JSON + template
>   starter-prompt chips).

Static-generated template library + blog CMS in the Next.js 15 app router, plus a thin "Open in Workspace" bridge to the backend `POST /api/sessions/from-template`.

---

## 1. Architecture

```
apps/web/content/
  templates/<slug>.mdx        ← frontmatter (metadata + docs) + JSON
  blog/<slug>.mdx             ← frontmatter (+ faq) + MDX body

lib/templates.ts  getAllTemplates() getTemplateBySlug() getAllTemplateSlugs()
lib/blog.ts       getAllPosts()     getPostBySlug()     getAllPostSlugs()
lib/searchIndex.ts  build-time {slug,title,description,category,provider,difficulty,tags}[]

app/templates/page.tsx          ← index (search + filters + grid)   [SSG]
app/templates/[slug]/page.tsx   ← detail (hero/preview/actions/docs/related) [SSG + generateMetadata]
app/blog/page.tsx               ← blog index                        [SSG]
app/blog/[slug]/page.tsx        ← article (MDX + copy + interactive JSON + FAQ) [SSG]

components/site/SiteHeader.tsx   ← shared nav (Home/Workspace/Templates/Blog/Pricing/GitHub)
components/templates/*           ← cards, filters, search, JSON preview, AI action bar, doc sections
components/blog/*                 ← blog card, FAQ, AI summary, copy button, interactive JSON

Open in Workspace:
  button → api.seedFromTemplate() → POST /api/sessions/from-template
         → router.push('/studio?session=<id>')
  /studio reads ?session, loads it, shows starter-prompt chips
```

**Key principle:** everything under `/templates` and `/blog` is statically generated at build for SEO + speed. The only runtime network call is the deliberate "Open in Workspace" action.

---

## 2. Dependencies

**Location:** `apps/web/package.json`. Install with `--legacy-peer-deps` (React 19 peer conflicts — see memory).

```jsonc
"gray-matter": "^4.0.3",          // frontmatter parsing
"next-mdx-remote": "^5.0.0",      // render MDX bodies (blog)
"shiki": "^1.0.0",                // build-time syntax highlighting (JSON + code snippets)
"fuse.js": "^7.0.0"               // optional: fuzzy client search (or hand-rolled filter)
```

```bash
cd apps/web && npm install gray-matter next-mdx-remote shiki fuse.js --legacy-peer-deps
```

> If avoiding MDX compilation complexity, blog bodies may be authored as plain Markdown and rendered with the already-present `react-markdown`; MDX is only needed for embedded `<InteractiveJson>` / `<OpenInWorkspace>` components inside articles (BL-02). Prefer `next-mdx-remote` for that.

---

## 3. Component Details

### 3.1 Content loaders — `lib/templates.ts`

```ts
import fs from 'node:fs';
import path from 'node:path';
import matter from 'gray-matter';

const DIR = path.join(process.cwd(), 'content/templates');

export interface TemplateMeta {
  id: string; slug: string; title: string; description: string;
  category: string; provider: string; difficulty: 'beginner'|'intermediate'|'advanced';
  estimated_read_time: string; tags: string[]; schema_version: string;
  featured: boolean; updated_at: string; author: string;
  starter_prompts: string[]; related_templates: string[]; related_blogs: string[];
  purpose: string; when_to_use: string;
  required_fields: string[]; optional_fields: string[];
  best_practices: string[]; security: string[];
}
export interface Template { meta: TemplateMeta; json: unknown; }

export function getAllTemplateSlugs(): string[] {
  return fs.readdirSync(DIR).filter(f => f.endsWith('.mdx')).map(f => f.replace(/\.mdx$/, ''));
}
export function getTemplateBySlug(slug: string): Template {
  const raw = fs.readFileSync(path.join(DIR, `${slug}.mdx`), 'utf8');
  const { data, content } = matter(raw);
  // JSON is a fenced ```json block in the body, or a sibling <slug>.json
  const json = extractJson(content, slug);
  return { meta: data as TemplateMeta, json };
}
export function getAllTemplates(): Template[] {
  return getAllTemplateSlugs().map(getTemplateBySlug);
}
```

`lib/blog.ts` mirrors this with `PostMeta` (adds `faq: {q:string;a:string}[]`) and returns `{ meta, body }`.

### 3.2 Search index — `lib/searchIndex.ts`

```ts
import { getAllTemplates } from './templates';
export function buildTemplateIndex() {
  return getAllTemplates().map(t => ({
    slug: t.meta.slug, title: t.meta.title, description: t.meta.description,
    category: t.meta.category, provider: t.meta.provider,
    difficulty: t.meta.difficulty, tags: t.meta.tags, featured: t.meta.featured,
  }));
}
```
Called in `/templates` server component; the array is passed to a client `<TemplateExplorer>` for filtering. No API.

### 3.3 `app/templates/[slug]/page.tsx` (Server Component)

```tsx
import { notFound } from 'next/navigation';
import { getAllTemplateSlugs, getTemplateBySlug } from '@/lib/templates';
import JsonLd from '@/components/JsonLd';

export function generateStaticParams() {
  return getAllTemplateSlugs().map(slug => ({ slug }));
}

export function generateMetadata({ params }: { params: { slug: string } }) {
  const { meta } = getTemplateBySlug(params.slug);
  const url = `https://jsonaistudio.com/templates/${meta.slug}`;
  return {
    title: `${meta.title} — JSON Template | JSON AI Studio`,
    description: meta.description,
    alternates: { canonical: url },
    openGraph: { title: meta.title, description: meta.description, url, type: 'article' },
    twitter: { card: 'summary_large_image', title: meta.title, description: meta.description },
  };
}

export default function TemplatePage({ params }: { params: { slug: string } }) {
  let tpl; try { tpl = getTemplateBySlug(params.slug); } catch { notFound(); }
  const { meta, json } = tpl;
  return (
    <>
      <JsonLd data={techArticleLd(meta)} />
      <JsonLd data={breadcrumbLd(meta)} />
      <TemplateHero meta={meta} json={json} />       {/* client: Open in Workspace */}
      <JsonPreview json={json} />                     {/* highlighted, read-only */}
      <AiActionBar meta={meta} json={json} />         {/* client: seed + push */}
      <TemplateDocs meta={meta} />
      <RelatedLists templates={meta.related_templates} blogs={meta.related_blogs} />
    </>
  );
}
```

### 3.4 `api.ts` — Open-in-Workspace client (OW-01)

```ts
export async function seedFromTemplate(
  templateSlug: string,
  templateTitle: string,
  json: unknown,
  starterPrompts: string[],
  apiKey: string,
): Promise<{ sessionId: string; working_json: Record<string, any>; starter_prompts: string[] }> {
  const res = await fetch(`${BASE}/sessions/from-template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
    body: JSON.stringify({ templateSlug, templateTitle, json, starterPrompts }),
  });
  if (!res.ok) throw new Error(`Open in Workspace failed: ${await res.text()}`);
  return res.json();
}
```

### 3.5 `AiActionBar.tsx` + `TemplateHero.tsx` (Client)

```tsx
'use client';
import { useRouter } from 'next/navigation';
import { seedFromTemplate } from '@/lib/api';
import { getApiKey } from '@/lib/authToken'; // existing X-API-Key accessor

const PRESET: Record<string, string> = {
  explain:  'Explain each field',
  validate: 'Validate this against best practices',
  improve:  'Suggest improvements',
  fix:      'Find and fix problems',
  customize:'',
};

async function open(action: string | null, meta, json, router) {
  const prompts = [PRESET[action ?? ''] , ...meta.starter_prompts].filter(Boolean);
  try {
    const { sessionId } = await seedFromTemplate(meta.slug, meta.title, json, prompts, getApiKey());
    router.push(`/studio?session=${sessionId}`);
  } catch (e) { toast.error(String(e)); }
}
// Download button = client blob, no network:
function download(meta, json) {
  const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(blob), download: `${meta.slug}.json` });
  a.click(); URL.revokeObjectURL(a.href);
}
```

### 3.6 `/studio` — consume `?session=` + starter prompts (OW-04)

**Location:** `apps/web/src/app/studio/page.tsx` + `context/SessionContext.tsx`.

- On mount, read `?session=<id>`. If present, call the existing session-load path (`GET /api/sessions/{id}` → hydrate `workingJson`) instead of creating a new session. Store `starterPrompts` from the create/get response (or from a short-lived `sessionStorage` handoff written before `router.push`).
- Render `starterPrompts` as clickable chips above/near the chat input in `ChatPanel`. Clicking a chip prefills the input (or sends via existing `sendMessage`). Chips clear after first send.

> **Watch the loading-unmount gotcha (memory `session-provider-loading-unmount`):** hydrating from `?session=` must **not** flip the global `loading` flag that renders `null` and wipes page-local state. Use a dedicated `hydrating` flag, mirroring how Explain avoided the global `loading`.

### 3.7 `components/site/SiteHeader.tsx` (N-01)

Extract the inline nav from `app/page.tsx` into a shared component; add `Templates` (`/templates`) and `Blog` (`/blog`) links. Reuse across landing, `/templates`, `/blog`. Keep the existing GitHub button + logo.

### 3.8 Blog rendering

- `app/blog/[slug]/page.tsx`: `getPostBySlug`, render `<AiSummary>` (from frontmatter), MDX body via `next-mdx-remote` with a components map exposing `<CopyBlock>`, `<InteractiveJson json={...}>` (wraps `JSONTree`), `<OpenInWorkspace slug json prompts>`. Render `<Faq items={meta.faq}/>` + `JsonLd` `FAQPage`.
- `components/blog/CopyButton.tsx`: copies code text, shows "Copied".

### 3.9 SEO helpers — `lib/ld.ts`

```ts
export const techArticleLd = (m) => ({
  '@context': 'https://schema.org', '@type': 'TechArticle',
  headline: m.title, description: m.description,
  datePublished: m.updated_at, author: { '@type': 'Person', name: m.author },
});
export const breadcrumbLd = (m) => ({
  '@context': 'https://schema.org', '@type': 'BreadcrumbList',
  itemListElement: [
    { '@type':'ListItem', position:1, name:'Home', item:'https://jsonaistudio.com' },
    { '@type':'ListItem', position:2, name:'Templates', item:'https://jsonaistudio.com/templates' },
    { '@type':'ListItem', position:3, name:m.title, item:`https://jsonaistudio.com/templates/${m.slug}` },
  ],
});
export const faqLd = (faq) => ({
  '@context':'https://schema.org', '@type':'FAQPage',
  mainEntity: faq.map(f => ({ '@type':'Question', name:f.q,
    acceptedAnswer:{ '@type':'Answer', text:f.a } })),
});
```

### 3.10 `app/sitemap.ts` (SEO-02)

```ts
import { getAllTemplateSlugs } from '@/lib/templates';
import { getAllPostSlugs } from '@/lib/blog';
// ...append to the returned array:
...getAllTemplateSlugs().map(slug => ({
  url: `https://jsonaistudio.com/templates/${slug}`,
  lastModified: new Date(), changeFrequency: 'monthly' as const, priority: 0.7,
})),
...getAllPostSlugs().map(slug => ({
  url: `https://jsonaistudio.com/blog/${slug}`,
  lastModified: new Date(), changeFrequency: 'monthly' as const, priority: 0.6,
})),
```
Also add static `/templates` and `/blog` index URLs.

---

## 4. Data Flow

### 4.1 Open in Workspace (happy path)
```
1. /templates/aws-iam → user clicks "Open in AI Workspace"
2. seedFromTemplate(slug,title,json,prompts,apiKey) → POST /api/sessions/from-template
3. 201 { sessionId, working_json, starter_prompts }
4. router.push('/studio?session=<id>')
5. studio hydrates session (GET /api/sessions/<id>), shows starter-prompt chips
6. user clicks a chip → existing sendMessage() → normal chat/diff flow
```

### 4.2 AI action button
```
Explain button → prompts = ["Explain each field", ...template.starter_prompts]
              → same seed + push, chip pre-selected/sent
```

### 4.3 Search/filter (client only)
```
/templates renders buildTemplateIndex() → <TemplateExplorer index>
typing/filter → filter array in memory → re-render grid; URL query synced
```

---

## 5. Error Handling

| Scenario | Response |
|----------|----------|
| Unknown template/blog slug | `notFound()` → Next 404 page |
| `seedFromTemplate` network/500 | toast error, stay on template page |
| Backend DB down (413/422) | toast error (should not happen for shipped templates) |
| No search results | empty-state card with "clear filters" |
| MDX parse error at build | build fails loudly (caught in CI/local build) |

---

## 6. Assumptions & Constraints

1. **SSG, not SSR.** All template/blog pages prerender at build; adding content = adding a file + rebuild.
2. **No template backend.** Search, filtering, related links are all resolved from static content at build/in the browser.
3. **Open in Workspace is the only runtime call** from these pages; anonymous `X-API-Key` is sufficient (OW-05).
4. **`prose` classes need explicit styling** — no `@tailwindcss/typography` (same constraint the Explain feature hit); style headings/code/tables via component maps.
5. **Preview is read-only** and must render without a backend.
6. **Content authoring is ongoing** — code ships the system + ~8–10 seed templates + 3–5 posts; the full catalog is a separate content stream.
7. **`--legacy-peer-deps`** required for installs (React 19).

---

## 7. Files Modified / New

| File | Action | Change |
|------|--------|--------|
| `apps/web/package.json` | **MODIFIED** | Add `gray-matter`, `next-mdx-remote`, `shiki`, `fuse.js` |
| `apps/web/content/templates/*.mdx` | **NEW** | Seed templates (8–10) |
| `apps/web/content/blog/*.mdx` | **NEW** | Seed blog posts (3–5) |
| `apps/web/src/lib/templates.ts` | **NEW** | Template content loader + types |
| `apps/web/src/lib/blog.ts` | **NEW** | Blog content loader + types |
| `apps/web/src/lib/searchIndex.ts` | **NEW** | Build-time search index |
| `apps/web/src/lib/ld.ts` | **NEW** | JSON-LD builders (TechArticle/Breadcrumb/FAQ) |
| `apps/web/src/lib/api.ts` | **MODIFIED** | Add `seedFromTemplate()` |
| `apps/web/src/app/templates/page.tsx` | **NEW** | Library index |
| `apps/web/src/app/templates/[slug]/page.tsx` | **NEW** | Template detail |
| `apps/web/src/app/blog/page.tsx` | **NEW** | Blog index |
| `apps/web/src/app/blog/[slug]/page.tsx` | **NEW** | Blog article |
| `apps/web/src/components/site/SiteHeader.tsx` | **NEW** | Shared nav (extracted) |
| `apps/web/src/components/templates/*` | **NEW** | Explorer, Card, Filters, Search, JsonPreview, AiActionBar, Hero, Docs, RelatedLists |
| `apps/web/src/components/blog/*` | **NEW** | BlogCard, AiSummary, Faq, CopyButton, InteractiveJson, OpenInWorkspace |
| `apps/web/src/app/page.tsx` | **MODIFIED** | Use `SiteHeader` |
| `apps/web/src/app/studio/page.tsx` | **MODIFIED** | Read `?session=`, hydrate, starter-prompt chips |
| `apps/web/src/context/SessionContext.tsx` | **MODIFIED** | Session hydrate-from-id + `starterPrompts` state (dedicated `hydrating` flag) |
| `apps/web/src/components/ChatPanel.tsx` | **MODIFIED** | Render starter-prompt chips |
| `apps/web/src/app/sitemap.ts` | **MODIFIED** | Enumerate template + blog URLs |

**No changes to:** `DiffViewer.tsx`, `VersionModal.tsx`, `WorkspaceSidebar.tsx`, `versionCache.ts`, auth flow.

---

## 8. Verification

### Manual Tests
1. **Build:** `npm run build` succeeds; `/templates/<slug>` + `/blog/<slug>` prerender (check `.next` output / no 404s).
2. **Index + search:** `/templates` lists cards; typing "iam" filters; category/difficulty filters combine and sync to `?query`.
3. **Detail page:** hero, highlighted JSON preview, AI action bar, all doc sections, related lists render.
4. **Open in Workspace:** click → lands on `/studio?session=<id>` with the template JSON loaded and starter-prompt chips visible; clicking a chip runs a normal chat turn.
5. **Download:** downloads `<slug>.json`, valid.
6. **Blog:** article renders MDX, copy buttons work, interactive JSON + Open-in-Workspace embeds work, FAQ shows.
7. **Nav:** Templates + Blog links present on landing + hub pages.
8. **SEO:** view-source shows canonical, OG, and JSON-LD (`TechArticle`/`BreadcrumbList`, `FAQPage` on blog); `sitemap.xml` includes new URLs; `robots.txt` doesn't block them.
9. **404:** `/templates/does-not-exist` → Next 404.
10. **Anonymous:** logged-out user can Open in Workspace.

Use the Browser pane (`preview_start {name}`) + `read_page` / `read_network_requests` to confirm the `from-template` POST and JSON-LD.

---

*End of frontend implementation guide. Feature branch: `templates`.*
