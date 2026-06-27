# 0008-cashify-react-json-view-over-native-or-alternatives-for-json-tree-rendering

**Date**: 2026-06-21
**Status**: Accepted

## Context

We need to render nested JSON as an expandable/collapsible tree view in the frontend. This is used in two places: (1) the upload/preview panel after uploading a JSON file, and (2) the diff viewer showing before/after versions side-by-side. We need a library that handles nested objects and arrays well.

## Decision

Use **`@cashify/react-json-view`** over native rendering or alternative libraries.

### Alternatives Considered

| Library | Pros | Cons | Why Not Chosen |
|---------|------|------|----------------|
| **Build our own** | Zero dependencies. Full control over styling and behavior. No risk of abandoned packages. | Significant time investment (~200+ lines for basic expand/collapse tree). Recursively handles nested objects/arrays — non-trivial edge cases. Duplicates effort we don't need for MVP. | Not chosen — a mature library saves 1-2 days of work and provides polished UX out of the box. |
| **react-json-view** | Mature, widely used, good React support. | Original repo is unmaintained (last commit 4+ years ago). Potential security risks from abandoned code. | Not chosen — unmaintained package with known issues unresolved. |
| **@cashify/react-json-view** (fork) | Maintained fork of react-json-view. Active community, regular updates. Expand/collapse built-in. Nested object support with zero config. Tree rendering for nested structures works out of the box. Easy to theme colors (important for diff states). | External dependency adds ~15KB to bundle size. Slight learning curve for theming API. | Chosen — maintains and actively developed, unlike the original. Provides exactly what we need: expand/collapse, nested support, zero config. |

## Implementation Notes

- Render tree via `<ReactJsonView src={json} theme="monokai" enabled={true} />` (or similar config).
- For diff viewer: render two side-by-side trees (before/after) using the same component with different `src` props.
- Color coding for diff states: green for added, orange for modified, red for deleted — apply via `names` prop and custom styling on tree nodes.
- Use `collapse` and `expand` callbacks to track expanded state in session state (for restoring expanded view after diffs).

## Consequences

### The good
- Expand/collapse of nested objects works out of the box — no custom component needed.
- Zero-config rendering: pass any JSON object, get a tree immediately.
- Easy to theme for diff states (green for +added, orange for ~modified, red for -deleted).
- Maintained fork means active security patches and bug fixes.

### The bad
- External dependency adds bundle weight (~15KB minified).
- The component's API surface (props like `names`, `transformData`, `onSelect`) requires reading the docs for advanced features.
- Theme customization has a learning curve — default colors may need overrides for our diff states.

## References

- [cashify/react-json-view GitHub](https://github.com/cashify/react-json-view)
- Related ADR: [#0003](0003-deepdiff-over-native-diff-for-backend-engine.md) (diff data shapes that feed into this viewer)
