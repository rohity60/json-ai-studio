"""Workspace persistence service (ADR-0018).

Only layer touching the workspaces/json_documents/json_versions tables.
Pure persistence: never reads or writes the in-memory session store —
load/save between a session and a workspace is a client concern.

Concurrency: document-count checks lock the workspace row FOR UPDATE and
version appends lock the document row FOR UPDATE, so limits hold under
concurrent saves. Version numbers are COALESCE(MAX)+1 — append-only,
never renumbered (requirements DB-06).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import session_factory
from ..db.models_orm import JsonDocument, JsonVersion, Workspace
from ..settings import get_settings
from .errors import ConflictError, DuplicateError, LimitExceededError, NotFoundError

logger = logging.getLogger("json_ai_studio.workspace_service")

DEFAULT_WORKSPACE_NAME = "default"


def _require_db():
    factory = session_factory()
    if factory is None:
        raise HTTPException(
            status_code=503,
            detail="Workspaces are temporarily unavailable (database not configured).",
        )
    return factory


def _to_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """Malformed path ids behave like missing resources, not 500s."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise NotFoundError("Workspace not found")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ws_summary(ws: Workspace, document_count: int) -> dict[str, Any]:
    return {
        "id": str(ws.id),
        "name": ws.name,
        "is_default": ws.is_default,
        "document_count": document_count,
        "updated_at": ws.updated_at,
    }


def _doc_summary(
    doc: JsonDocument, version_count: int, latest_version_number: int
) -> dict[str, Any]:
    return {
        "id": str(doc.id),
        "tag": doc.tag,
        "version_count": version_count,
        "latest_version_number": latest_version_number,
        "updated_at": doc.updated_at,
    }


def _version_dict(v: JsonVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "version_number": v.version_number,
        "label": v.label,
        "content": v.content,
        "created_at": v.created_at,
    }


async def _get_owned_workspace(
    db: AsyncSession, user_id: uuid.UUID, ws_id: str, *, for_update: bool = False
) -> Workspace:
    """Ownership check. Someone else's workspace -> 404, never 403."""
    stmt = select(Workspace).where(
        Workspace.id == _to_uuid(ws_id), Workspace.user_id == user_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    ws = (await db.execute(stmt)).scalar_one_or_none()
    if ws is None:
        raise NotFoundError("Workspace not found")
    return ws


async def _get_owned_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    ws_id: str,
    doc_id: str,
    *,
    for_update: bool = False,
) -> JsonDocument:
    ws = await _get_owned_workspace(db, user_id, ws_id)
    stmt = select(JsonDocument).where(
        JsonDocument.id == _to_uuid(doc_id), JsonDocument.workspace_id == ws.id
    )
    if for_update:
        stmt = stmt.with_for_update()
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise NotFoundError("JSON document not found")
    return doc


# -- provisioning ------------------------------------------------------------


async def ensure_default_workspace(user_id: uuid.UUID) -> None:
    """Idempotently create the user's default workspace (requirements P-01).

    Keyed on is_default (not name) so it survives renames; the partial
    unique index uq_workspaces_user_default closes the concurrent-first-
    request race — the loser's insert raises and is swallowed.
    """
    factory = _require_db()
    async with factory() as db:
        existing = (
            await db.execute(
                select(Workspace.id).where(
                    Workspace.user_id == user_id, Workspace.is_default.is_(True)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        try:
            db.add(
                Workspace(user_id=user_id, name=DEFAULT_WORKSPACE_NAME, is_default=True)
            )
            await db.commit()
            logger.info("default workspace created user_id=%s", user_id)
        except IntegrityError:
            await db.rollback()  # concurrent request won the race — fine


# -- workspaces --------------------------------------------------------------


async def list_workspaces(user_id: uuid.UUID) -> list[dict[str, Any]]:
    factory = _require_db()
    async with factory() as db:
        doc_count = (
            select(func.count(JsonDocument.id))
            .where(JsonDocument.workspace_id == Workspace.id)
            .scalar_subquery()
        )
        rows = (
            await db.execute(
                select(Workspace, doc_count)
                .where(Workspace.user_id == user_id)
                .order_by(Workspace.created_at)
            )
        ).all()
        return [_ws_summary(ws, count) for ws, count in rows]


async def create_workspace(user_id: uuid.UUID, name: str) -> dict[str, Any]:
    factory = _require_db()
    async with factory() as db:
        ws = Workspace(user_id=user_id, name=name)
        db.add(ws)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise DuplicateError("name")
        await db.refresh(ws)
        logger.info("workspace created id=%s user_id=%s", ws.id, user_id)
        return _ws_summary(ws, 0)


async def rename_workspace(user_id: uuid.UUID, ws_id: str, name: str) -> dict[str, Any]:
    factory = _require_db()
    async with factory() as db:
        ws = await _get_owned_workspace(db, user_id, ws_id)
        ws.name = name
        ws.updated_at = _now()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise DuplicateError("name")
        await db.refresh(ws)
        count = (
            await db.execute(
                select(func.count(JsonDocument.id)).where(
                    JsonDocument.workspace_id == ws.id
                )
            )
        ).scalar_one()
        return _ws_summary(ws, count)


async def delete_workspace(user_id: uuid.UUID, ws_id: str) -> None:
    factory = _require_db()
    async with factory() as db:
        ws = await _get_owned_workspace(db, user_id, ws_id)
        if ws.is_default:
            raise ConflictError("The default workspace cannot be deleted.")
        await db.delete(ws)  # documents + versions cascade
        await db.commit()
        logger.info("workspace deleted id=%s user_id=%s", ws_id, user_id)


# -- documents ---------------------------------------------------------------


async def list_documents(user_id: uuid.UUID, ws_id: str) -> list[dict[str, Any]]:
    factory = _require_db()
    async with factory() as db:
        ws = await _get_owned_workspace(db, user_id, ws_id)
        rows = (
            await db.execute(
                select(
                    JsonDocument,
                    func.count(JsonVersion.id),
                    func.coalesce(func.max(JsonVersion.version_number), 0),
                )
                .outerjoin(JsonVersion, JsonVersion.document_id == JsonDocument.id)
                .where(JsonDocument.workspace_id == ws.id)
                .group_by(JsonDocument.id)
                .order_by(JsonDocument.created_at)
            )
        ).all()
        return [_doc_summary(doc, count, latest) for doc, count, latest in rows]


async def save_document(
    user_id: uuid.UUID, ws_id: str, tag: str, versions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Bulk save: new document + 1..N versions in one transaction (J-02)."""
    settings = get_settings()
    if len(versions) > settings.json_max_versions:
        raise LimitExceededError("versions", settings.json_max_versions)

    factory = _require_db()
    async with factory() as db:
        # FOR UPDATE serializes the document-count check against concurrent saves.
        ws = await _get_owned_workspace(db, user_id, ws_id, for_update=True)
        count = (
            await db.execute(
                select(func.count(JsonDocument.id)).where(
                    JsonDocument.workspace_id == ws.id
                )
            )
        ).scalar_one()
        if count >= settings.workspace_max_jsons:
            raise LimitExceededError("jsons", settings.workspace_max_jsons)

        doc = JsonDocument(
            workspace_id=ws.id, tag=tag, last_version_number=len(versions)
        )
        db.add(doc)
        try:
            await db.flush()  # surfaces duplicate tag before inserting versions
        except IntegrityError:
            await db.rollback()
            raise DuplicateError("tag")
        for number, payload in enumerate(versions, start=1):
            db.add(
                JsonVersion(
                    document_id=doc.id,
                    version_number=number,
                    label=payload.get("label"),
                    content=payload["content"],
                )
            )
        await db.commit()
        await db.refresh(doc)
        logger.info(
            "document saved id=%s ws=%s tag=%s versions=%d",
            doc.id,
            ws.id,
            tag,
            len(versions),
        )
        return _doc_summary(doc, len(versions), len(versions))


async def get_document(user_id: uuid.UUID, ws_id: str, doc_id: str) -> dict[str, Any]:
    factory = _require_db()
    async with factory() as db:
        doc = await _get_owned_document(db, user_id, ws_id, doc_id)
        versions = (
            (
                await db.execute(
                    select(JsonVersion)
                    .where(JsonVersion.document_id == doc.id)
                    .order_by(JsonVersion.version_number)
                )
            )
            .scalars()
            .all()
        )
        return {
            "id": str(doc.id),
            "tag": doc.tag,
            "versions": [_version_dict(v) for v in versions],
        }


async def rename_document(
    user_id: uuid.UUID, ws_id: str, doc_id: str, tag: str
) -> dict[str, Any]:
    factory = _require_db()
    async with factory() as db:
        doc = await _get_owned_document(db, user_id, ws_id, doc_id)
        doc.tag = tag
        doc.updated_at = _now()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise DuplicateError("tag")
        await db.refresh(doc)
        count, latest = (
            await db.execute(
                select(
                    func.count(JsonVersion.id),
                    func.coalesce(func.max(JsonVersion.version_number), 0),
                ).where(JsonVersion.document_id == doc.id)
            )
        ).one()
        return _doc_summary(doc, count, latest)


async def delete_document(user_id: uuid.UUID, ws_id: str, doc_id: str) -> None:
    factory = _require_db()
    async with factory() as db:
        doc = await _get_owned_document(db, user_id, ws_id, doc_id)
        await db.delete(doc)  # versions cascade
        await db.commit()
        logger.info("document deleted id=%s ws=%s", doc_id, ws_id)


# -- versions ----------------------------------------------------------------


async def append_versions(
    user_id: uuid.UUID, ws_id: str, doc_id: str, versions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Append-only save into an existing document (V-01). Atomic."""
    settings = get_settings()
    factory = _require_db()
    async with factory() as db:
        # FOR UPDATE serializes concurrent appends on the same document.
        doc = await _get_owned_document(db, user_id, ws_id, doc_id, for_update=True)
        count = (
            await db.execute(
                select(func.count(JsonVersion.id)).where(
                    JsonVersion.document_id == doc.id
                )
            )
        ).scalar_one()
        if count + len(versions) > settings.json_max_versions:
            raise LimitExceededError("versions", settings.json_max_versions)

        # Numbers come from the document's historical high-water mark, not
        # MAX() of surviving rows — a deleted top version is never reused
        # (requirements DB-06).
        created: list[JsonVersion] = []
        for offset, payload in enumerate(versions, start=1):
            v = JsonVersion(
                document_id=doc.id,
                version_number=doc.last_version_number + offset,
                label=payload.get("label"),
                content=payload["content"],
            )
            db.add(v)
            created.append(v)
        doc.last_version_number += len(versions)
        doc.updated_at = _now()
        await db.commit()
        for v in created:
            await db.refresh(v)
        logger.info(
            "versions appended doc=%s count=%d now_at=%d",
            doc.id,
            len(versions),
            doc.last_version_number,
        )
        return [_version_dict(v) for v in created]


async def delete_version(
    user_id: uuid.UUID, ws_id: str, doc_id: str, version_id: str
) -> None:
    factory = _require_db()
    async with factory() as db:
        doc = await _get_owned_document(db, user_id, ws_id, doc_id, for_update=True)
        try:
            target_id = uuid.UUID(version_id)
        except (ValueError, AttributeError, TypeError):
            raise NotFoundError("Version not found")
        count = (
            await db.execute(
                select(func.count(JsonVersion.id)).where(
                    JsonVersion.document_id == doc.id
                )
            )
        ).scalar_one()
        if count == 1:
            exists = (
                await db.execute(
                    select(JsonVersion.id).where(
                        JsonVersion.id == target_id,
                        JsonVersion.document_id == doc.id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                raise NotFoundError("Version not found")
            # A document must keep >= 1 version (V-02).
            raise ConflictError(
                "Cannot delete the last version; delete the JSON document instead."
            )
        result = await db.execute(
            sa_delete(JsonVersion).where(
                JsonVersion.id == target_id, JsonVersion.document_id == doc.id
            )
        )
        if result.rowcount == 0:
            raise NotFoundError("Version not found")
        await db.commit()
        logger.info("version deleted id=%s doc=%s", version_id, doc_id)
