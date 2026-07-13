"""Workspace endpoints (ADR-0018). Bearer-only persistence layer.

Thin router: resolve principal, call workspace_service, map domain errors
to HTTP codes. Structured 409 details (limit_exceeded / duplicate) pass
through verbatim so the frontend can render targeted guidance.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import Principal, get_principal
from ..models import (
    AppendVersionsRequest,
    CreateWorkspaceRequest,
    JsonDocumentDetail,
    JsonDocumentSummary,
    RenameJsonRequest,
    SaveJsonRequest,
    WorkspaceJsonVersion,
    WorkspaceSummary,
)
from ..services import workspace_service
from ..services.errors import ConflictError, NotFoundError

logger = logging.getLogger("json_ai_studio.controllers.workspaces")

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _require_user(principal: Principal) -> uuid.UUID:
    """Workspace routes are bearer-only; anonymous gets the login CTA."""
    if principal.kind != "user" or principal.user_id is None:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Login required to use workspaces.",
                "login_available": True,
            },
        )
    return principal.user_id


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConflictError):
        # LimitExceededError/DuplicateError carry a structured detail dict.
        detail = getattr(exc, "detail", None) or str(exc)
        return HTTPException(status_code=409, detail=detail)
    raise exc


@router.get("", response_model=list[WorkspaceSummary])
async def endpoint_list_workspaces(
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    return await workspace_service.list_workspaces(user_id)


@router.post("", response_model=WorkspaceSummary, status_code=201)
async def endpoint_create_workspace(
    body: CreateWorkspaceRequest,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.create_workspace(user_id, body.name)
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.patch("/{workspace_id}", response_model=WorkspaceSummary)
async def endpoint_rename_workspace(
    workspace_id: str,
    body: CreateWorkspaceRequest,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.rename_workspace(
            user_id, workspace_id, body.name
        )
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.delete("/{workspace_id}", status_code=204)
async def endpoint_delete_workspace(
    workspace_id: str,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        await workspace_service.delete_workspace(user_id, workspace_id)
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)
    return Response(status_code=204)


@router.get("/{workspace_id}/jsons", response_model=list[JsonDocumentSummary])
async def endpoint_list_documents(
    workspace_id: str,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.list_documents(user_id, workspace_id)
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.post(
    "/{workspace_id}/jsons", response_model=JsonDocumentSummary, status_code=201
)
async def endpoint_save_document(
    workspace_id: str,
    body: SaveJsonRequest,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.save_document(
            user_id,
            workspace_id,
            body.tag,
            [v.model_dump() for v in body.versions],
        )
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.get("/{workspace_id}/jsons/{document_id}", response_model=JsonDocumentDetail)
async def endpoint_get_document(
    workspace_id: str,
    document_id: str,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.get_document(user_id, workspace_id, document_id)
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.patch("/{workspace_id}/jsons/{document_id}", response_model=JsonDocumentSummary)
async def endpoint_rename_document(
    workspace_id: str,
    document_id: str,
    body: RenameJsonRequest,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.rename_document(
            user_id, workspace_id, document_id, body.tag
        )
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.delete("/{workspace_id}/jsons/{document_id}", status_code=204)
async def endpoint_delete_document(
    workspace_id: str,
    document_id: str,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        await workspace_service.delete_document(user_id, workspace_id, document_id)
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)
    return Response(status_code=204)


@router.post(
    "/{workspace_id}/jsons/{document_id}/versions",
    response_model=list[WorkspaceJsonVersion],
    status_code=201,
)
async def endpoint_append_versions(
    workspace_id: str,
    document_id: str,
    body: AppendVersionsRequest,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        return await workspace_service.append_versions(
            user_id,
            workspace_id,
            document_id,
            [v.model_dump() for v in body.versions],
        )
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)


@router.delete(
    "/{workspace_id}/jsons/{document_id}/versions/{version_id}", status_code=204
)
async def endpoint_delete_version(
    workspace_id: str,
    document_id: str,
    version_id: str,
    principal: Principal = Depends(get_principal),
):
    user_id = _require_user(principal)
    try:
        await workspace_service.delete_version(
            user_id, workspace_id, document_id, version_id
        )
    except (NotFoundError, ConflictError) as exc:
        raise _map_error(exc)
    return Response(status_code=204)
