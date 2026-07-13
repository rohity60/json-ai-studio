# 0018-workspaces-as-persistence-layer-over-sessions

**Date**: 2026-07-12
**Status**: Accepted

## Context

Today the only durable artifacts are the `users` table (ADR-0015) and the browser's IndexedDB mirror (ADR-0014). Everything a user works on — working JSON, version snapshots, conversation — lives in one in-memory session (ADR-0006/0013) and dies with it. Users need to organize work: a **workspace** holds up to 5 JSON documents, each JSON holds up to 5 versions, each JSON is identified by a user-given **tag**. Anonymous users keep a friction-free local flow; logging in unlocks durable, named workspaces in Postgres.

The open design question: do workspaces replace the session model, or layer on top of it?

## Decision

**Workspaces are a pure persistence layer in Postgres, layered above the untouched in-memory session runtime.** The session remains the only runtime workbench (working JSON + pending diffs + chat). Workspace content flows in and out of sessions explicitly:

- **Load**: selecting a workspace JSON hydrates a fresh/current session with that document's versions and its latest version as working JSON (reusing the bulk-restore seam from ADR-0014).
- **Save (explicit)**: a user-initiated Save copies the session's versions — plus a snapshot of the working JSON if it differs from the latest version — into the workspace document. No auto-persist; unsaved edits stay session-local, which is what makes the "save your work?" guard popups (UI requirement) meaningful.

### Domain model

```
users 1───n workspaces 1───n json_documents 1───n json_versions
```

New tables (Alembic migration; SQLAlchemy 2.0 async, same stack as ADR-0015):

```sql
workspaces
  id           UUID PK
  user_id      UUID FK → users.id ON DELETE CASCADE
  name         VARCHAR(100) NOT NULL         -- user-given
  is_default   BOOLEAN NOT NULL DEFAULT false
  created_at   TIMESTAMPTZ DEFAULT now()
  updated_at   TIMESTAMPTZ DEFAULT now()
  UNIQUE (user_id, name)

json_documents
  id                  UUID PK
  workspace_id        UUID FK → workspaces.id ON DELETE CASCADE
  tag                 VARCHAR(100) NOT NULL  -- user-given identifier, rename allowed
  last_version_number INTEGER NOT NULL DEFAULT 0
                      -- historical high-water mark: next number = this + 1,
                      -- so a deleted top version's number is never reused
  created_at          TIMESTAMPTZ DEFAULT now()
  updated_at          TIMESTAMPTZ DEFAULT now()
  UNIQUE (workspace_id, tag)

json_versions
  id             UUID PK
  document_id    UUID FK → json_documents.id ON DELETE CASCADE
  version_number INTEGER NOT NULL            -- monotonic per document
  label          VARCHAR(255)
  content        JSONB NOT NULL
  created_at     TIMESTAMPTZ DEFAULT now()
  UNIQUE (document_id, version_number)
```

`json_documents` carries **no content column**: a document *is* its versions, and "latest version loads for work" falls out of `max(version_number)`. Saving a dirty working JSON creates a new version (counts toward the limit) rather than a shadow working-copy column — one storage concept, no divergence.

### Indexing

Every hot query is served by the composite UNIQUE constraints — each leads with the FK column, so **no separate single-column FK indexes** (they would duplicate the unique index's leftmost prefix and only add write overhead):

| Index | Backs |
|-------|-------|
| `uq_workspaces_user_name` `(user_id, name)` | list-workspaces-by-user (prefix scan); duplicate-name check; `users` cascade delete |
| `uq_workspaces_user_default` `(user_id) WHERE is_default` — partial unique | at-most-one default per user (rename-safe provisioning race guard); default-workspace lookup on login |
| `uq_json_documents_ws_tag` `(workspace_id, tag)` | list-documents-by-workspace; duplicate-tag check; workspace cascade delete |
| `uq_json_versions_doc_number` `(document_id, version_number)` | versions-ordered-by-number; `MAX(version_number)` (backward index scan); next-number assignment; document cascade delete |
| `users` PK / `workspaces` PK / `json_documents` PK | ownership checks are PK lookups + `user_id` compare — no extra index |

`json_versions.content` (JSONB) gets **no GIN index** — content is never queried by key at MVP, only fetched whole.

**Why btree, not hash** (considered and rejected): Postgres hash indexes cannot enforce UNIQUE and cannot be multi-column — every index above is a composite unique constraint, so hash is structurally impossible for them. The workload also isn't equality-only: `MAX(version_number)`/`ORDER BY version_number` need ordered scans and list-by-owner needs leftmost-prefix scans, both btree-only. Supplementary single-column hash indexes on FKs would duplicate coverage the composite btrees already provide at this scale (≤5 docs × ≤5 versions) — pure write overhead.

Note: there is **no pre-existing version table** to migrate — session version snapshots were never in Postgres (in-memory + IndexedDB only, ADR-0013/0014). `json_versions` is greenfield.

### Key rules

- **Default workspace, logged-in**: created idempotently (`is_default = true`, name `default`) during user provisioning (same upsert seam as ADR-0015). Active on login. Cannot be deleted; can be renamed.
- **Default workspace, anonymous**: virtual — it is simply today's session + IndexedDB mirror (ADR-0014 unchanged). Never touches Postgres. Upload and version-create keep working anonymously; Save and add-second-JSON require login (401 → frontend login CTA popup, same pattern as quota errors in ADR-0015).
- **Limits block, never evict**: 5 JSONs/workspace, 5 versions/JSON (Settings knobs `WORKSPACE_MAX_JSONS`, `JSON_MAX_VERSIONS`). Exceeding → 409 with structured detail; user must delete to make room. No silent data loss.
- **Auth**: all `/api/workspaces/*` endpoints require an Auth0 bearer (ADR-0015). Anonymous X-API-Key requests to these endpoints → 401. Without `DATABASE_URL`, they 503 like other DB-backed routes.
- **Contract-first**: endpoints and schemas land in `openapi/spec.yaml` first, then Pydantic (`models.py`), then hand-written TS mirrors (ADR-0011/0012).
- **Active workspace/document is client state** (localStorage next to sessionId). No server-side "current selection" — the server stays stateless about UI focus.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Workspaces replace sessions (persist working state directly) | Rewrites the chat/diff/SSE runtime that works today; couples every keystroke to Postgres; kills the graceful no-DB anonymous mode. |
| Auto-persist every upload/version for logged-in users | No draft state, constant writes, and the required "save before switching?" popups become meaningless. Explicit Save matches the versions UX users already know. |
| Working-copy column on `json_documents` | Two sources of truth for content; contradicts "latest version loads for work". Dirty-save-as-version keeps one concept. |
| Auto-generated document tags (slug/filename) | Product wants tags as meaningful identifiers ("similar to version"); user-given + unique-per-workspace, rename allowed. |
| Evict-oldest at limit | Silent data loss; block-with-409 is predictable and the popup can offer cleanup. |
| Anonymous workspaces in Postgres keyed by X-API-Key | Orphan rows, GC policy needed, no real benefit over the existing IndexedDB mirror. |

## Addendum (2026-07-13) — Tier 1 auto-save UX

Explicit Save-with-guards proved irritating in use (the dirty-guard modal fired on every context switch; a hand-tracked dirty flag produced "unsaved changes → already saved" contradictions). First remediation, frontend-only, no schema change:

- **Switching auto-saves.** `guardDirty()` no longer opens a modal; it silently appends pending edits into the active document, then proceeds. A first-ever save (no document yet) still opens the Save dialog because it needs a tag; a hard failure (version limit) stops the switch with a toast.
- **Status pill replaces the Save button as the primary signal.** Header shows `saved` / `saving…` / `unsaved (click to save)` / `local (log in)`. Persistence is a visible state, not a triggered event. The explicit button becomes "Save as…" (new/copy only).
- **`UnsavedChangesModal` retired.** Dirty tracking keyed on persisted-version *content* (not a snapshot ref), so selecting an already-saved version reads clean.

The end state (Tier 2, deferred) is true continuous auto-save of the working copy — a `working_content` head on `json_documents`, which revisits this ADR's "working-copy column" rejection under the new UX goal. Tracked in `apps/web/ai/feature/workspaces`.

## Consequences

- Three new tables via one Alembic migration; schema changes continue through `alembic revision --autogenerate`.
- `openapi/spec.yaml` grows 11 endpoints / ~8 schemas (see `apps/api/ai/feature/workspaces/requirements.md`); the "13 endpoints, 18 schemas" counts in docs need updating.
- Session store, chat flow, diff engine untouched — workspaces only add load/save edges.
- Login-after-anonymous-work flow: the browser still holds everything (IndexedDB), so "log in then Save" needs no server-side migration step — the client saves its local state through the normal Save API.
- Deleting a user cascades workspaces → documents → versions.
- Per-user workspace count is currently unbounded — acceptable at MVP; add `MAX_WORKSPACES_PER_USER` knob when needed.
