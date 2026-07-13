"""JSON AI Studio — Pydantic models (canonical wire format per ADR-0011).

All schemas derived from openapi/spec.yaml. These models serialise directly to
JSON via FastAPI, so field names and types are the single source of truth for
the frontend's TypeScript types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from uuid import uuid4

from pydantic import BaseModel, Field

# -- Core Domain Models --


class Session(BaseModel):
    """Full session state (in-memory, per ADR-0006)."""

    id: str
    name: str | None = None
    working_json: dict[str, Any]
    baseline_json: dict[str, Any] = {}
    versions: list[VersionSnapshot] = []
    conversation_history: list[ChatTurn] = []
    applied_diffs: list[str] = []
    rejected_diffs: list[str] = []
    created_at: datetime
    updated_at: datetime


class VersionSnapshot(BaseModel):
    """Immutable point-in-time JSON snapshot."""

    id: str
    parent_id: str | None = None
    json_data: dict[str, Any]
    label: str
    created_at: datetime


class ChatTurn(BaseModel):
    """Single chat message with role and optional attached diffs."""

    role: Literal["user", "assistant"]
    content: str
    diffs: list[DiffEntry] | None = None


# -- Wire Contracts --


class DiffEntry(BaseModel):
    """One field-level change (add / modify / delete)."""

    path: str
    operation: Literal["add", "modify", "delete"]
    old_value: Any | None = None
    new_value: Any | None = None
    id: str = ""  # UNIQUE ID — backend generates, frontend uses for accept/reject


class ValidationErrorItem(BaseModel):
    """One validation error with optional JSON Pointer path."""

    path: str | None = None
    message: str


class Error(BaseModel):
    """Wire contract for all error responses (ADR-0007)."""

    error: str
    hint: str | None = None


# -- Request / Response Wrappers --


class CreateSessionRequest(BaseModel):
    name: str


class SessionResponse(Session):
    """Full session state returned by GET and POST endpoints."""

    pass


class CreateVersionRequest(BaseModel):
    label: str
    json_data: dict[str, Any]


class SelectVersionRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/versions/select."""

    versionId: str


class ChatRequest(BaseModel):
    session_id: str
    conversation_history: list[ChatTurn] = []
    working_json: dict[str, Any]
    message: str


class UploadResponse(BaseModel):
    session_id: str
    parsed_json: dict[str, Any]
    schema_summary: SchemaSummary | None = None


class SchemaSummary(BaseModel):
    top_level_keys: list[str]
    nested_depth: int
    array_lengths: dict[str, int] = {}


class ValidateRequest(BaseModel):
    json_data: dict[str, Any]


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationErrorItem] = []


class DiffAcceptResponse(BaseModel):
    success: bool
    working_json: dict[str, Any]
    baseline_json: dict[str, Any] = {}
    diffs: list[DiffEntry] = []
    validation_passed: bool = True


class DiffRejectResponse(BaseModel):
    success: bool
    working_json: dict[str, Any]
    baseline_json: dict[str, Any] = {}


class RestoreVersionsRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/versions/restore.

    Snapshots come from the browser's IndexedDB cache after a backend
    restart; ids, labels, parent chains, and timestamps are preserved.
    """

    versions: list[VersionSnapshot]
    working_json: dict[str, Any] | None = None
    baseline_json: dict[str, Any] | None = None
    active_version_id: str | None = None


class QuotaErrorDetail(BaseModel):
    """Structured 402/429 detail body (spec: QuotaError, ADR-0015)."""

    error: str
    hint: str | None = None
    login_available: bool
    retry_after: int | None = None


class CreditsInfo(BaseModel):
    monthly_limit: int
    used: float
    remaining: float
    billing_cycle_start: str


class UserProfile(BaseModel):
    """Response body for GET /api/me (spec: UserProfile, ADR-0015)."""

    id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    plan: str
    credits: CreditsInfo
    per_minute_token_limit: int


# -- Workspaces (ADR-0018) --


class WorkspaceSummary(BaseModel):
    """List/response shape for a workspace (spec: WorkspaceSummary)."""

    id: str
    name: str
    is_default: bool
    document_count: int
    updated_at: datetime


class CreateWorkspaceRequest(BaseModel):
    """Body for POST /api/workspaces and PATCH /api/workspaces/{id}."""

    name: str = Field(min_length=1, max_length=100)


class RenameJsonRequest(BaseModel):
    """Body for PATCH .../jsons/{documentId} (tag rename)."""

    tag: str = Field(min_length=1, max_length=100)


class JsonDocumentSummary(BaseModel):
    """List/response shape for a document (spec: JsonDocumentSummary)."""

    id: str
    tag: str
    version_count: int
    latest_version_number: int
    updated_at: datetime


class WorkspaceJsonVersion(BaseModel):
    """One persisted snapshot (spec: WorkspaceJsonVersion)."""

    id: str
    version_number: int
    label: str | None = None
    content: dict[str, Any]
    created_at: datetime


class JsonDocumentDetail(BaseModel):
    """GET .../jsons/{documentId} — versions ordered by version_number."""

    id: str
    tag: str
    versions: list[WorkspaceJsonVersion]


class NewVersionPayload(BaseModel):
    """One snapshot to persist (spec: NewVersionPayload)."""

    label: str | None = None
    content: dict[str, Any]


class SaveJsonRequest(BaseModel):
    """Body for POST .../jsons — bulk save of a new document."""

    tag: str = Field(min_length=1, max_length=100)
    versions: list[NewVersionPayload] = Field(min_length=1, max_length=5)


class AppendVersionsRequest(BaseModel):
    """Body for POST .../jsons/{documentId}/versions — append-only."""

    versions: list[NewVersionPayload] = Field(min_length=1)
