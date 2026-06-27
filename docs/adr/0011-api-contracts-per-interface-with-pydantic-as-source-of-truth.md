# 0011-api-contracts-per-interface-with-pydantic-as-source-of-truth

**Date**: 2026-06-21
**Status**: Accepted

## Context

The frontend and backend communicate over JSON. We need to decide: (a) how to organize the shape definitions that both sides must agree on, and (b) what serves as the canonical source of truth when there's a mismatch risk between Python models and TypeScript types.

Currently we have no shared package or codegen tooling — the backend produces Pydantic model serialization output and the frontend consumes it. Without discipline, these drift over time.

## Decision 1: Per-Interface Shapes Over Shared Models

Use **per-interface shapes** (one canonical shape per wire contract) instead of a single monolithic shared model or separate ad-hoc shapes scattered across files.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Per-interface shapes** — one canonical DiffEntry, one ChatRequest, one ValidationResponse, etc. Each has its own model/type pair (Pydantic ↔ TypeScript) | Small, focused, easy to update one at a time. No monolithic model file that becomes impossible to maintain. Clear ownership: each shape belongs to exactly one interface | More files — but only 4-6 shapes needed for MVP. Trivial to manage. | Chosen — fits the MVP scale perfectly (4 wire interfaces total). Each shape maps to exactly one backend method or endpoint. |
| **Single shared model** — one `models.py` / `types.ts` file containing every type for all endpoints | Everything in one place; easy to grep | Becomes a massive unsearchable file at any non-trivial scale. Adding a new field means modifying the same line everyone else is changing. Merge conflicts guaranteed. | Not chosen — this pattern collapses under its own weight beyond MVP. |
| **Separate ad-hoc shapes** — each developer writes their own type/model as needed, no agreement enforced | Fast initial development, zero discipline required | Divergence guaranteed — frontend and backend will serialize/deserialize differently. Hard to debug "why is this field missing?" | Not chosen — wire contracts are non-negotiable; ad-hoc types guarantee silent data loss. |

### Wire Interfaces Requiring Per-Interface Shapes

| # | Interface Name | Wire Path | Shape Key |
|---|----------------|-----------|-----------|
| 1 | **DiffEntry** | SSE stream from `POST /api/chat` + `POST /api/diff` | `{ path, operation ("add"\|"modify"\|"delete"), old_value, new_value }` |
| 2 | **ChatRequest** | Body of `POST /api/chat` (frontend → backend) | `{ conversation_history: [{ role, content }], working_json }` |
| 3 | **ValidationResponse** | Body of `POST /api/validate` (backend → frontend) | `{ valid: bool, errors: [{ path?, message }] }` |
| 4 | **ErrorResponse** | All non-2xx responses | `{ error: string, hint?: string }` |

## Decision 2: Pydantic Models as Wire Format = Source of Truth (Option A)

Use **Pydantic models on the backend** as the canonical source of truth. The frontend TypeScript types are "comment-only" documentation — no codegen, no sync scripts, just `@see` comments pointing to the Python model in the ADRs.

### Alternatives Considered

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| **Pydantic models = wire format = single source of truth** (Option A) | Fast API development — Pydantic serializes directly to JSON for the frontend. No codegen, no sync scripts, no shared package. Frontend types are lightweight comments only. Divergence risk exists but is low at MVP scale; TypeScript will catch mismatches at compile time anyway. | Potential for field name drift if a backend developer changes a model without updating the frontend comment. Low impact: TS compiles with `unknown` or loose shapes, and runtime errors from wrong shape are immediately visible in DevTools. | Chosen — best trade-off for MVP scale. The wire format is determined by Python model fields + serialization output. No shared package to manage. |
| **Strict dual-source (codegend types)** — generate TypeScript from Pydantic using `prisma` / `json-schema-to-typescript` / custom script | Guaranteed alignment between backend and frontend; no drift possible. Codegen runs on build or CI. | Significant tooling overhead: a `shared-types/` package, codegen scripts in CI, npm publish step. Over-engineered for MVP with only 4 wire interfaces. Maintenance burden outweighs benefit at this scale. | Not chosen — the complexity of maintaining a codegen pipeline isn't justified for 4 shapes and MVP timeline. |
| **Frontend as source of truth** — define TS types first, then build Pydantic models to match | Useful when frontend dictates UX requirements; TypeScript-first teams may prefer this. | Slow initial setup — both sides wait on each other to agree on shapes before coding begins. No net benefit over backend-as-truth for an API-first product. | Not chosen — we are building an API-first product; the backend's Pydantic models serialize to the wire, making them naturally authoritative. |

## Implementation Pattern

### Backend: Pydantic Model (Canonical)

```python
# apps/api/src/json_ai_studio/models.py
from pydantic import BaseModel

class DiffEntry(BaseModel):
    path: str
    operation: Literal["add", "modify", "delete"]
    old_value: Any
    new_value: Any
```

The wire format is exactly `DiffEntry.model_json_schema()` → serialized to JSON via FastAPI. This is what the frontend consumes. No additional transformation layer needed.

### Frontend: TypeScript Type with Reference Comment (Documentation-Only)

```typescript
// apps/web/src/types/diff.ts
/**
 * DiffEntry — shape matching backend model:
 * @see docs/adr/0011-api-contracts-per-interface-with-pydantic-as-source-of-truth.md
 * @see apps/api/src/json_ai_studio/models.py:DiffEntry
 */
export interface DiffEntry {
  path: string;
  operation: "add" | "modify" | "delete";
  old_value: unknown;
  new_value: unknown;
}
```

Key characteristics:
- **No codegen** — manually written types with `@see` comments pointing to the Python model and ADR.
- **Loose shapes where possible** — use `unknown` for JSON values rather than strict typing, since working_json content is arbitrary user-provided schema.
- **Drift tolerance** — if a backend field changes, the frontend catches it at compile time (TypeScript compiler error) or runtime (DevTools network tab). Not ideal but acceptable for MVP.

## Consequences

### The good
- Fast iteration: backend changes a Pydantic field → frontend picks up the new shape at runtime without codegen rebuilds.
- Zero tooling overhead: no codegen scripts, no `shared-types/` package, no npm publish step.
- Each per-interface shape is small and focused — easy to reason about and update independently.
- Pydantic models are directly serializable to JSON via FastAPI — the wire format matches the model exactly.

### The bad
- **Potential for field name drift** between Python model and frontend TypeScript type if a developer changes one without updating the other. This is low-risk at MVP scale (4 interfaces, ~10 endpoints) and becomes non-problematic once we have tests covering wire contracts.
- Frontend types are loose documentation — no compile-time guarantee that they match the backend's serialized output. TypeScript will warn at build time, but `unknown` values absorb most mismatch risk.

## References

- Related ADR: [#0002](0002-litellm-over-openai-sdk-for-llm-integration.md) (`litestllm` integration layer — determines backend LLM response format)
- Related ADR: [#0010](0010-lucide-react-over-native-or-alternatives-for-icon-library.md) (frontend UI rendering — consumes DiffEntry shapes)
