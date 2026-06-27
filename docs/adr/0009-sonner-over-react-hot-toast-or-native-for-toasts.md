# 0009-sonner-over-react-hot-toast-or-native-for-toast-notifications

**Date**: 2026-06-21
**Status**: Accepted

## Context

The PRD requires toast notifications for success and error events from the API (requirement X-03). We need a lightweight notification library that works well with React and Next.js.

## Decision

Use **`sonner`** over `react-hot-toast` or building native toasts ourselves.

### Alternatives Considered

| Library | Pros | Cons | Why Not Chosen |
|---------|------|------|----------------|
| **Build our own** | Zero dependencies. Full control over appearance and behavior. No external risk. | Significant implementation effort (~100 lines for basic toast system with positioning, auto-dismiss, stacking). Edge cases: multiple toasts stacking, accessibility (focus management), mobile viewport issues. | Not chosen — a standard library provides polish we'd spend days building. |
| **react-hot-toast** | Mature, widely used, good React support. Active community. Familiar API (`toast.success()`, `toast.error()`). | Slightly heavier bundle (~5KB minified + CSS). Less visually polished by default compared to sonner. Fewer built-in variants (no built-in rich toast support). | Not chosen — sonner provides better default styling with less code to write. |
| **sonner** | Beautiful out-of-the-box defaults. Zero-config — just call `toast.success()`. Lightweight (~2KB gzipped). No CSS files needed (uses Tailwind under the hood). Perfect fit for Next.js + Tailwind projects. Built-in variants: success, error, info, warning. Easy to customize via a provider wrapper. | Slightly newer than react-hot-toast — fewer examples online. Fewer advanced features (e.g., no built-in rich text toasts in free version). | Chosen — the best balance of lightweight + polished + zero-config for our use case. |

## Implementation Notes

- Add `<Toaster />` component to the root layout (`src/app/layout.tsx`).
- Use `toast.success('Uploaded successfully')`, `toast.error('Invalid JSON: line 3')`, etc.
- Style via Tailwind class overrides in the provider wrapper (default theme matches our color palette).

## Consequences

### The good
- Zero-config setup — drop `<Toaster />` in layout and call `toast.success()` / `toast.error()` anywhere.
- Beautiful out-of-the-box defaults that match modern React apps.
- Lightweight (~2KB gzipped) — minimal impact on bundle size.
- Built-in variants (success, error, info, warning) cover all our use cases from the PRD (X-03).

### The bad
- Newer library — fewer Stack Overflow answers compared to established alternatives like react-hot-toast.
- Limited rich toast support in free version (no custom components inside toasts).
- Must install Tailwind for styling to work properly (sonner assumes Tailwind classes are available).

## References

- [sonner GitHub](https://github.com/wobsoriano/sonner)
- Related PRD requirement: X-03 — "Toast notifications for success/error events from the API"
