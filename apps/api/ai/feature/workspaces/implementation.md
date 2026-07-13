# JSON AI Studio — Workspaces Feature Implementation Guide (Backend)

**Feature branch:** `workspace`
**Requirements:** `requirements.md`
**ADR:** `docs/adr/0018-workspaces-as-persistence-layer-over-sessions.md`

---

## 1. Architecture

```
/api/workspaces* (bearer only)
  → get_principal (auth.py) — 401 with login_available for anonymous
  → controllers/workspaces.py — parse, call service, map domain errors → HTTP
  → services/workspace_service.py — ownership, limits, transactions
  → db/models_orm.py: Workspace / JsonDocument / JsonVersion (Postgres, Alembic)

Session runtime (store, chat, diffs): UNTOUCHED. Load/save happen client-side
through GET document + existing restore seam / bulk save endpoints.
```

**Key principle:** workspaces are DB-only. No coupling to `db/session_store.py`. The server never copies between a session and a workspace — the browser does, via existing session endpoints plus the new workspace endpoints.

---

## 2. Component Details

### 2.1 `settings.py` — Limit Knobs

**Action:** Add two fields next to the quota fields (pydantic-settings picks up `WORKSPACE_MAX_JSONS` / `JSON_MAX_VERSIONS` env vars automatically).

```python
    # Workspace limits (ADR-0018)
    workspace_max_jsons: int = 5
    json_max_versions: int = 5
```

### 2.2 `db/models_orm.py` — Three ORM Models

**Action:** Append after `User`. `JSONB` from `sqlalchemy.dialects.postgresql`.

```python
class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_workspaces_user_name"),
        # At most one default workspace per user, survives renames.
        Index(
            "uq_workspaces_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # No index=True on FKs anywhere in this feature: each composite UNIQUE
    # leads with the FK column and covers list/duplicate/cascade lookups
    # (ADR-0018 "Indexing").
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(100))
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["JsonDocument"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class JsonDocument(Base):
    __tablename__ = "json_documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "tag", name="uq_json_documents_ws_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    tag: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="documents")
    versions: Mapped[list["JsonVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="JsonVersion.version_number",
    )


class JsonVersion(Base):
    __tablename__ = "json_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_json_versions_doc_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("json_documents.id", ondelete="CASCADE")
    )
    version_number: Mapped[int]
    label: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped["JsonDocument"] = relationship(back_populates="versions")
```

### 2.3 Alembic Migration

```bash
cd apps/api
uv run alembic revision --autogenerate -m "create workspaces tables"
# review generated apps/api/alembic/versions/0002_*.py — confirm the partial
# unique index (postgresql_where) survived autogenerate; add manually if not
uv run alembic upgrade head
```

### 2.4 `openapi/spec.yaml` — Contract First (ADR-0011/0012)

**Action:** Add 11 paths + schemas. Wire format is **snake_case** (matches existing `json_data` / `login_available` style). operationIds:

`listWorkspaces`, `createWorkspace`, `renameWorkspace`, `deleteWorkspace`, `listWorkspaceJsons`, `saveWorkspaceJson`, `getWorkspaceJson`, `renameWorkspaceJson`, `deleteWorkspaceJson`, `appendJsonVersions`, `deleteJsonVersion`.

New schemas: `WorkspaceSummary`, `CreateWorkspaceRequest`, `RenameWorkspaceRequest`, `JsonDocumentSummary`, `JsonDocumentDetail`, `WorkspaceJsonVersion`, `SaveJsonRequest`, `AppendVersionsRequest`, `WorkspaceConflictDetail`.

### 2.5 `models.py` — Pydantic Wire Schemas

**Action:** Append; field names verbatim from spec.yaml.

```python
class WorkspaceSummary(BaseModel):
    id: str
    name: str
    is_default: bool
    document_count: int
    updated_at: datetime


class CreateWorkspaceRequest(BaseModel):
    name: str


class RenameWorkspaceRequest(BaseModel):
    name: str | None = None  # workspace rename
    tag: str | None = None   # document rename (PATCH .../jsons/{docId})


class WorkspaceJsonVersion(BaseModel):
    id: str
    version_number: int
    label: str | None = None
    content: dict[str, Any]
    created_at: datetime


class JsonDocumentSummary(BaseModel):
    id: str
    tag: str
    version_count: int
    latest_version_number: int
    updated_at: datetime


class JsonDocumentDetail(BaseModel):
    id: str
    tag: str
    versions: list[WorkspaceJsonVersion]  # ordered by version_number


class NewVersionPayload(BaseModel):
    label: str | None = None
    content: dict[str, Any]


class SaveJsonRequest(BaseModel):
    tag: str
    versions: list[NewVersionPayload]  # 1..5, enforced in service


class AppendVersionsRequest(BaseModel):
    versions: list[NewVersionPayload]
```

### 2.6 `services/errors.py` — Structured Conflicts

**Action:** Keep the generic hierarchy (controllers already map `NotFoundError → 404`, `ConflictError → 409`). Add two `ConflictError` subclasses that carry the structured detail from requirements L-03:

```python
class LimitExceededError(ConflictError):
    """A workspace/document limit blocks the write (never evicts)."""

    def __init__(self, limit_type: str, limit: int):
        self.detail = {"error": "limit_exceeded", "limit_type": limit_type, "limit": limit}
        super().__init__(f"{limit_type} limit of {limit} reached")


class DuplicateError(ConflictError):
    """UNIQUE constraint would be violated (workspace name / document tag)."""

    def __init__(self, field: str):
        self.detail = {"error": "duplicate", "field": field}
        super().__init__(f"duplicate {field}")
```

### 2.7 `services/workspace_service.py` — New Service

**Action:** New file. Only layer touching the DB for workspaces. Reuses the `_require_db()` 503 pattern from `user_service.py`.

Functions (all `async`, all take `user_id: uuid.UUID` first and verify ownership → `NotFoundError`, never 403):

```python
async def ensure_default_workspace(user_id) -> None
    # SELECT id FROM workspaces WHERE user_id=:u AND is_default LIMIT 1
    # → missing: INSERT (name="default", is_default=True); the partial unique
    #   index uq_workspaces_user_default makes a concurrent double-insert
    #   raise IntegrityError → swallow (someone else won the race).
    # Survives renames because it keys on is_default, not name.

async def list_workspaces(user_id) -> list[dict]          # + document_count subquery
async def create_workspace(user_id, name) -> dict          # DuplicateError("name")
async def rename_workspace(user_id, ws_id, name) -> dict   # NotFound / DuplicateError
async def delete_workspace(user_id, ws_id) -> None         # is_default → ConflictError

async def list_documents(user_id, ws_id) -> list[dict]     # version_count + max(version_number)
async def save_document(user_id, ws_id, tag, versions) -> dict
    # ONE transaction:
    #   ownership check → count docs FOR UPDATE on workspace row
    #   count == workspace_max_jsons → LimitExceededError("jsons", limit)
    #   len(versions) not in 1..json_max_versions → InvalidInputError
    #   insert document → DuplicateError("tag") on IntegrityError
    #   insert versions numbered 1..n
async def get_document(user_id, ws_id, doc_id) -> dict      # + versions ordered
async def rename_document(user_id, ws_id, doc_id, tag) -> dict
async def delete_document(user_id, ws_id, doc_id) -> None

async def append_versions(user_id, ws_id, doc_id, versions) -> list[dict]
    # ONE transaction:
    #   SELECT document row FOR UPDATE  (serialize concurrent appends)
    #   current + len(new) > json_max_versions → LimitExceededError("versions", limit)
    #   next number = doc.last_version_number + 1  (historical high-water mark
    #   column on json_documents — NOT MAX() of surviving rows, so a deleted
    #   top version's number is never reused; DB-06)
async def delete_version(user_id, ws_id, doc_id, version_id) -> None
    # last remaining version → ConflictError("delete the document instead")
```

### 2.8 `controllers/workspaces.py` — New Router

**Action:** New file, mirroring `controllers/users.py` style. Register by adding it to the `routers` list in `controllers/__init__.py` (main.py loops `app.include_router` over it — no main.py change).

```python
router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _require_user(principal: Principal) -> uuid.UUID:
    if principal.kind != "user" or principal.user_id is None:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Login required to use workspaces.",
                "login_available": True,   # frontend httpError() reads this → login CTA
            },
        )
    return principal.user_id
```

Every endpoint: `principal: Principal = Depends(get_principal)` → `_require_user` → service call inside `try/except`: `NotFoundError → 404`, `LimitExceededError/DuplicateError → HTTPException(409, detail=e.detail)`, other `ConflictError → 409` (string detail), `InvalidInputError → 422`.

### 2.9 `services/user_service.py` — Provisioning Hook

**Action:** At the end of `upsert_from_claims()` (still inside the function, after the userinfo backfill), call `workspace_service.ensure_default_workspace(user.id)`. First authenticated request thus guarantees the default workspace (requirements P-01) with no explicit signup endpoint — same philosophy as ADR-0015 upsert-in-dependency.

---

## 3. Data Flow

### 3.1 Save new document (happy path)

```
1. POST /api/workspaces/{ws}/jsons  Authorization: Bearer <token>
   {"tag": "payment-config", "versions": [{"label": "v1", "content": {...}}, ...]}
2. get_principal → Principal(kind=user) → user upserted, default ws ensured
3. save_document(): ownership ok, 3/5 docs, tag free
4. One transaction: document + versions 1..n inserted
5. 201 {"id": "...", "tag": "payment-config", "version_count": 2,
        "latest_version_number": 2, "updated_at": "..."}
```

### 3.2 Limit blocks the write

```
1. POST .../jsons into a workspace with 5 documents
2. save_document() counts 5 == workspace_max_jsons
3. LimitExceededError("jsons", 5) → controller →
   409 {"detail": {"error": "limit_exceeded", "limit_type": "jsons", "limit": 5}}
4. Nothing written (single transaction rolled back)
```

### 3.3 Anonymous request

```
1. GET /api/workspaces with X-API-Key
2. get_principal → kind=anonymous → _require_user →
   401 {"detail": {"message": "Login required to use workspaces.", "login_available": true}}
```

### 3.4 No database configured

```
1. Any workspace call, DATABASE_URL unset
2. _require_db() → 503 (same behavior as /api/me; anonymous session flow unaffected)
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `401` | Anonymous principal on any workspace route | `{"detail": {"message": ..., "login_available": true}}` |
| `404` | Workspace/document/version missing **or owned by another user** | `{"detail": "Workspace not found"}` (never 403 — don't leak existence) |
| `409` | 6th document / 6th version | `{"detail": {"error": "limit_exceeded", "limit_type": "jsons"\|"versions", "limit": 5}}` |
| `409` | Duplicate workspace name / document tag | `{"detail": {"error": "duplicate", "field": "name"\|"tag"}}` |
| `409` | Delete default workspace / delete last version | string detail with guidance |
| `422` | 0 or >5 versions in save payload; empty tag/name | FastAPI/InvalidInputError detail |
| `503` | `DATABASE_URL` unset | `{"detail": "... database not configured ..."}` |

---

## 5. Assumptions & Constraints

1. **No session-store coupling.** The server never reads/writes sessions on workspace routes; hydration is a client concern (existing restore endpoint).
2. **snake_case wire format**, consistent with `json_data`/`login_available` in the existing contract.
3. **Version numbers are append-only** — `COALESCE(MAX)+1` under `FOR UPDATE`; deletes never renumber (DB-06).
4. **Default workspace idempotency keys on `is_default`**, not the name — rename-safe; partial unique index closes the race.
5. **Limits read from `get_settings()`** at call time — tests/ops can tune via env without code changes.
6. **Full JSONB per version** — no delta/dedup storage (MVP).
7. **`black .` after editing** any Python file (project rule).

---

## 6. Files Modified

| File | Action | Change |
|------|--------|--------|
| `openapi/spec.yaml` | **MODIFIED** | +11 paths, +9 schemas |
| `apps/api/src/json_ai_studio/settings.py` | **MODIFIED** | +`workspace_max_jsons`, +`json_max_versions` |
| `apps/api/src/json_ai_studio/db/models_orm.py` | **MODIFIED** | +`Workspace`, +`JsonDocument`, +`JsonVersion` |
| `apps/api/alembic/versions/0002_*.py` | **NEW** | Autogenerated migration (verify partial index) |
| `apps/api/src/json_ai_studio/models.py` | **MODIFIED** | +9 Pydantic schemas |
| `apps/api/src/json_ai_studio/services/errors.py` | **MODIFIED** | +`LimitExceededError`, +`DuplicateError` |
| `apps/api/src/json_ai_studio/services/workspace_service.py` | **NEW** | All workspace business logic |
| `apps/api/src/json_ai_studio/services/user_service.py` | **MODIFIED** | +`ensure_default_workspace` call in `upsert_from_claims` |
| `apps/api/src/json_ai_studio/controllers/workspaces.py` | **NEW** | Router, 11 endpoints |
| `apps/api/src/json_ai_studio/controllers/__init__.py` | **MODIFIED** | Register router in `routers` list |

**No changes to:** `db/session_store.py`, `services/chat_service.py`, `services/session_service.py`, `services/version_service.py`, `auth.py`, `utils.py`, `main.py`.

---

## 7. Verification

Needs `DATABASE_URL` + `AUTH0_*` env (compose db on host port 5433) and a real bearer token from the web app.

1. **Provisioning:** log in via web, `GET /api/workspaces` → exactly one workspace, `is_default: true`, name `default`. Call again → still one.
2. **CRUD:** create/rename/delete a second workspace via Swagger; deleting `default` → 409.
3. **Save + limits:** save a document with 2 versions → 201; save 4 more docs; 6th → 409 `limit_exceeded/jsons`. Append versions to one doc up to 5; 6th → 409 `limit_exceeded/versions`.
4. **Duplicate tag:** same tag twice in one workspace → 409 `duplicate/tag`; same tag in another workspace → 201.
5. **Isolation:** second Auth0 user cannot `GET` the first user's workspace (404).
6. **Anonymous:** `curl -H "X-API-Key: k" localhost:8000/api/workspaces` → 401 with `login_available: true`.
7. **No-DB mode:** unset `DATABASE_URL`, restart → workspace routes 503, session/chat flow still works.
8. **Cascade:** delete a workspace → its `json_documents`/`json_versions` rows gone (check via psql).

---

*End of implementation guide. Feature branch: `workspace`.*
