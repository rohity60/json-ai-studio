---
name: landing-page-swap
description: Swap landing pages in a Next.js app router project — move one version to root, set noindex on the other, verify canonical URLs via curl
source: auto-skill
extracted_at: '2026-07-11T16:44:59.127Z'
---

## Task: Swap landing pages (making v2 primary, v1 secondary)

In a Next.js App Router project, swap the primary landing page from v1 to v2 and ensure proper SEO via canonical URLs and robots metadata.

### Step 1: Move files

The goal is that the root path `/` serves the new landing (v2) and the old landing (v1) is accessible at `/v1`.

Next.js filesystem routing means you move the page file, not edit route mappings:

1. **Move v2's page to root:**
   ```bash
   mv apps/web/src/app/v2/[page].tsx apps/web/src/app/page.tsx
   ```
2. **Move old v1 page to v1 directory:**
   ```bash
   mkdir -p apps/web/src/app/v1
   mv apps/web/src/app/[page].tsx apps/web/src/app/v1/page.tsx
   ```
3. **Delete empty v2 directory:**
   ```bash
   rmdir apps/web/src/app/v2 2>/dev/null
   ```

Verify file system state after:
```bash
ls apps/web/src/app/ | grep -E 'page\.tsx|v1|v2'
ls apps/web/src/app/v1/ 2>/dev/null
```

### Step 2: Update metadata

Both pages need aligned metadata. Check each file and adjust:

**Root `page.tsx` (v2 — PRIMARY):**
- Title and description should reflect the new v2 content.
- `alternates.canonical` → `'/'`
- `openGraph.url` → `'/'`
- `openGraph.title` / `og:description` — copy from `layout.tsx`.
- `robots.ts` already permits root via `allow: '/'`.
- Remove any "preview" notes from the old file.

**`/v1/page.tsx` (v1 — SECONDARY):**
- `robots: { index: false, follow: false }` to prevent index competition.
- `alternates.canonical` → `'/'` (points to the new primary).

**`layout.tsx` metadata:**
Ensure the root metadata matches v2 (not v1). Check:
- `title.default` and `title.template`
- `description`
- `keywords` (add 'json validator', 'json transform' if they belong to v2)
- `openGraph.title`, `openGraph.description`, `openGraph.url` (`'/'`)
- `openGraph.siteName`, `openGraph.type` (`'website'`)
- `twitter.card` → `'summary_large_image'`
- `robots: { index: true, follow: true }`

### Step 3: Verify via curl after dev server start

After restarting the dev server, verify in parallel:

```bash
# Check root metadata
curl -s http://localhost:3002/ | grep -oE '(rel="canonical"|property="og:[a-z]+" content="[^"]*"|name="og:[a-z]+" content="[^"]*)"'

# Check v1 robots noindex
curl -s http://localhost:3002/v1 | grep -oE 'name="robots" content="[^"]*"'

# Confirm v2 route is gone (404)
curl -sI http://localhost:3002/v2 | grep "HTTP"
```

Expected results:
| Route | Expected |
|-------|----------|
| `/` | v2 content, `canonical → /`, `og:url → /`, `index, follow` |
| `/v1` | v1 content, `noindex, nofollow`, `canonical → /` |
| `/v2` | 404 (empty directory) |

### Troubleshooting

- **v2 still serves at `/`:** Ensure the page file is named `page.tsx` inside `v2/` and was moved correctly, not just the directory renamed.
- **404 on `/`:** Restart the dev server; Next.js may not detect file moves while the process is running.
- **v1 returns 404:** Check the file path — it must be `src/app/v1/page.tsx`, not `src/app/v2/page.tsx` inside the v1 directory.
- **Port conflicts:** `lsof -ti:3002 | xargs kill -9` before restart.
