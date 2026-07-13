# Backend Requirements — JSON AI Studio Workspaces Feature

Only what the **server / API layer** must implement. Companion: `apps/web/ai/feature/workspaces/requirements.md`, ADR-0018.

A **workspace** belongs to one user and holds up to 5 **JSON documents**; each document is identified by a user-given **tag** (unique per workspace) and holds up to 5 **versions**. Workspaces are a pure Postgres persistence layer above the untouched in-memory session runtime (ADR-0018): load hydrates a session, explicit Save copies session state back.

---

## 1. Database Schema

| # | Requirement | Priority |
|---|-------------|----------|
| DB-01 | Three new tables via one Alembic migration: `workspaces`, `json_documents`, `json_versions` (ORM models in `db/models_orm.py`, SQLAlchemy 2.0 async — same stack as ADR-0015). | MVP |
| DB-02 | `workspaces`: `id UUID PK`, `user_id FK → users.id`, `name VARCHAR(100)`, `is_default BOOL DEFAULT false`, `created_at`, `updated_at`. `UNIQUE (user_id, name)`. | MVP |
| DB-03 | `json_documents`: `id UUID PK`, `workspace_id FK → workspaces.id`, `tag VARCHAR(100)`, `created_at`, `updated_at`. `UNIQUE (workspace_id, tag)`. **No content column** — a document is its versions. | MVP |
| DB-04 | `json_versions`: `id UUID PK`, `document_id FK → json_documents.id`, `version_number INT` (monotonic per document, server-assigned), `label VARCHAR(255)`, `content JSONB`, `created_at`. `UNIQUE (document_id, version_number)`. | MVP |
| DB-05 | All FKs `ON DELETE CASCADE`: deleting a user removes workspaces → documents → versions. | MVP |
| DB-06 | Deleting a version never renumbers surviving versions; next `version_number` = historical max + 1. | MVP |

---

## 2. Default Workspace & Provisioning

| # | Requirement | Priority |
|---|-------------|----------|
| P-01 | Every logged-in user gets a default workspace (`is_default = true`, name `default`), created idempotently during user provisioning (same upsert seam as ADR-0015; safe under concurrent first requests). | MVP |
| P-02 | Default workspace cannot be deleted (`409`); rename allowed. | MVP |
| P-03 | Anonymous users get **no server-side workspace**: their default workspace is virtual — today's in-memory session + IndexedDB mirror (ADR-0014, unchanged). | MVP |

---

## 3. Auth, Limits, Config

| # | Requirement | Priority |
|---|-------------|----------|
| A-01 | All `/api/workspaces*` routes require an Auth0 bearer (ADR-0015). Anonymous `X-API-Key` → `401` with `login_available: true` (frontend shows login CTA popup). | MVP |
| A-02 | Without `DATABASE_URL`, workspace routes return `503`; anonymous session flow keeps working (graceful no-DB mode preserved). | MVP |
| A-03 | Ownership enforced on every route: workspace not owned by the bearer's user → `404` (not `403` — don't leak existence). | MVP |
| L-01 | Limits **block, never evict**: 6th document in a workspace or 6th version on a document → `409`, nothing written. | MVP |
| L-02 | Limits are Settings fields (pydantic-settings): `WORKSPACE_MAX_JSONS=5`, `JSON_MAX_VERSIONS=5`. | MVP |
| L-03 | Structured `409` detail: `{"error": "limit_exceeded", "limit_type": "jsons"\|"versions", "limit": 5}` or `{"error": "duplicate", "field": "name"\|"tag"}`. | MVP |

---

## 4. Endpoints — Workspaces

Contract lands in `openapi/spec.yaml` first, then Pydantic `models.py`, then hand-written TS mirrors (ADR-0011/0012).

| # | Requirement | Priority |
|---|-------------|----------|
| W-01 | `GET /api/workspaces` — list caller's workspaces: `{id, name, isDefault, documentCount, updatedAt}`. | MVP |
| W-02 | `POST /api/workspaces` — create `{name}` → `201` workspace. `409` duplicate name. | MVP |
| W-03 | `PATCH /api/workspaces/{wsId}` — rename `{name}`. `409` duplicate, `404` not found/not owned. | MVP |
| W-04 | `DELETE /api/workspaces/{wsId}` — delete + cascade. `409` if `is_default`. | MVP |

---

## 5. Endpoints — JSON Documents

| # | Requirement | Priority |
|---|-------------|----------|
| J-01 | `GET /api/workspaces/{wsId}/jsons` — list documents: `{id, tag, versionCount, latestVersionNumber, updatedAt}`. | MVP |
| J-02 | `POST /api/workspaces/{wsId}/jsons` — **Save new document**: `{tag, versions: [{label, content}]}`. Bulk write (document + versions) in one transaction — mirrors the restore endpoint's shape. `409` document limit or duplicate tag; `422` if payload has 0 or >5 versions. | MVP |
| J-03 | `GET /api/workspaces/{wsId}/jsons/{docId}` — document + all versions ordered by `version_number` (client loads latest into session). | MVP |
| J-04 | `PATCH /api/workspaces/{wsId}/jsons/{docId}` — rename tag. `409` duplicate. | MVP |
| J-05 | `DELETE /api/workspaces/{wsId}/jsons/{docId}` — delete document + versions (frees a slot). | MVP |

---

## 6. Endpoints — Versions

| # | Requirement | Priority |
|---|-------------|----------|
| V-01 | `POST /api/workspaces/{wsId}/jsons/{docId}/versions` — **Save into existing document**: `{versions: [{label, content}]}`, appends only; `409` if append would exceed `JSON_MAX_VERSIONS`. Atomic — all or nothing. | MVP |
| V-02 | `DELETE /api/workspaces/{wsId}/jsons/{docId}/versions/{versionId}` — delete one version (frees a slot). Deleting the last remaining version → `409` (client should delete the document instead). | MVP |

---

## 7. Service Layering (ADR-0013)

| # | Requirement | Priority |
|---|-------------|----------|
| S-01 | New router `controllers/workspaces.py`: parse request, call service, map domain errors → HTTP codes. | MVP |
| S-02 | New `services/workspace_service.py`: limits, default-workspace rules, ownership checks, bulk save transactions. Only layer touching the DB session. | MVP |
| S-03 | New domain exceptions in `services/errors.py`: `WorkspaceNotFound`, `DocumentNotFound`, `VersionNotFound`, `LimitExceeded`, `DuplicateName`, `DuplicateTag`, `DefaultWorkspaceProtected`. | MVP |
| S-04 | Session store, chat service, diff engine, upload flow: **no changes**. Workspaces only add load/save edges around the existing session runtime. | MVP |
| S-05 | No server-side "active workspace" state — UI selection is client state only; server stays stateless about focus. | MVP |

---

## 8. Data Flow

### 8.1 Save (new document)

```
1. Frontend POST /api/workspaces/{ws}/jsons {tag, versions:[...session versions, dirty working snapshot]}
2. Bearer resolved → user; workspace ownership checked (else 404)
3. Document count checked (5 → 409 limit_exceeded); tag uniqueness checked (409 duplicate)
4. One transaction: insert document + versions (numbered 1..n)
5. 201 with document summary
```

### 8.2 Save (existing document, append versions)

```
1. Frontend POST .../jsons/{docId}/versions {versions: [only snapshots not yet persisted]}
2. Ownership + existence checks
3. current_count + len(new) > 5 → 409 limit_exceeded, nothing written
4. Versions appended with next monotonic numbers → 201
```

### 8.3 Load document into session

```
1. Frontend GET .../jsons/{docId} → document + versions
2. Client hydrates session via existing restore seam (ADR-0014); latest version becomes working JSON
3. No server-side coupling between workspaces and session store
```

### 8.4 Anonymous user hits workspace API

```
1. Request with X-API-Key to /api/workspaces
2. 401 {"login_available": true}
3. Frontend shows login CTA popup
```

---

## 9. Excluded from MVP

- Workspace sharing / multi-user access
- Server-side active-workspace persistence
- Per-user workspace count cap (unbounded; add `MAX_WORKSPACES_PER_USER` knob later)
- Version delta/dedup storage (full JSONB per version)
- Server-side migration of anonymous IndexedDB state at login (client saves through normal Save API)
- Conversation history persistence

---

*End of requirements. Feature branch: `workspace`. Implementation files: `db/models_orm.py` + Alembic migration (schema), `controllers/workspaces.py` (router), `services/workspace_service.py` (logic), `services/errors.py` (exceptions), `settings.py` (limit knobs), `models.py` + `openapi/spec.yaml` (contract).*
