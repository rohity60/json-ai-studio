# 0010-lucide-react-over-native-or-alternatives-for-icon-library

**Date**: 2026-06-21
**Status**: Accepted

## Context

The PRD UI requires icons for various elements: upload icon, diff arrows (before/after toggle), version badges, checkmarks for accepted changes, and other UI polish. We need an icon library that is clean, tree-shakeable, and works well with Next.js.

## Decision

Use **`lucide-react`** over native SVGs or alternative icon libraries.

### Alternatives Considered

| Library | Pros | Cons | Why Not Chosen |
|---------|------|------|----------------|
| **Native SVG inline** | Zero dependencies. Full control over every path and style. No bundle cost for unused icons. | Tedious to write inline SVGs for each icon. Code gets cluttered quickly with `<svg>` elements scattered across components. Harder to maintain consistent sizing/coloring across the app. | Not chosen — 10+ icons would add ~500 lines of repeated `<svg>` boilerplate. A library gives us consistency and tree-shaking. |
| **react-icons (Font Awesome / Material / Feather)** | Massive icon collection (~8000+ icons) from multiple sources. Easy to switch between icon sets (Feather, Material, etc.). Good variety for every use case. | Heavy bundle size if importing from multiple icon sets. Some icon sets have licensing restrictions. Less consistent design language across different source libraries. | Not chosen — we only need ~10-15 icons for MVP; a massive collection is overkill and the multi-source approach hurts visual consistency. |
| **lucide-react** | Clean, modern line-style icons designed as a unified set (~1500 icons). Tree-shakeable — only imported icons are bundled (~2KB per icon used). Works naturally with Next.js App Router (static icons at build time). Consistent design language: all icons share the same stroke-width and visual weight. Already used by most Next.js starters (shadcn/ui default). Easy import pattern: `import { Upload, ArrowRight } from 'lucide-react'`. | Slightly fewer total icons than react-icons (1500 vs 8000+). Some niche icons missing. | Chosen — best balance of quality, size, and consistency for a modern React/Next.js project. The design system is unified (not mixed sources), which matters for a polished UI. |

## Icons Needed for MVP

Based on the frontend requirements:

| Icon | Usage |
|------|-------|
| `Upload` (from `lucide-react`) | Drag-and-drop zone button |
| `ArrowRight` / `ArrowLeft` | Before/after diff panel toggle |
| `Check` | Accepted change indicator |
| `X` | Rejected change indicator |
| `FileJson2` | JSON file icon in session sidebar |
| `History` | Version history badge |
| `Copy` | Export/copy to clipboard action |
| `MessageSquare` | Chat message bubble indicator |
| `Sparkles` | AI-generated content marker |

All 9 icons are included in `lucide-react`'s base set. Total estimated bundle: ~18KB for all used icons.

## Implementation Notes

```tsx
import { Upload, ArrowRight, Check } from 'lucide-react';

// Tree-shakeable — only these 3 icons add to the bundle
<Upload className="w-5 h-5 text-muted-foreground" />
<ArrowRight className="w-4 h-4" />
<Check className="w-4 h-4 text-green-600" />
```

- Use Tailwind `className` for sizing and coloring (consistent with our design system).
- Static icons render at build time (no client-side JS overhead in the App Router).

## Consequences

### The good
- Clean, modern line-style icons that look polished out of the box.
- Tree-shakeable — only icons we import add to bundle size (~2KB each).
- Consistent design language across all 1500+ icons in the set.
- Already the default for shadcn/ui (Next.js starter stack) — well-documented examples.
- Static rendering at build time (App Router friendly).

### The bad

- Bundle cost scales linearly with icon count (~2KB per import). Not ideal for apps using hundreds of icons (we only need ~10).
- Some niche icons missing (e.g., certain brand logos or abstract symbols).
- Must install Tailwind to style icons effectively via `className` (already a project dependency).

## References

- [lucide GitHub](https://github.com/lucide-icons/lucide)
- Related PRD requirement: Section 9 — "UX / Quality" — empty states and tooltips need icon polish
