"""SQLAlchemy ORM models (ADR-0015).

Named models_orm to avoid clashing with the wire-format models.py.
Only signed-up users live in the database; sessions stay in-memory
(ADR-0013/0014). Schema changes go through Alembic migrations under
apps/api/alembic/versions/.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    auth0_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255))
    picture: Mapped[str | None] = mapped_column(String(1024))

    plan: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    monthly_credit_limit: Mapped[int] = mapped_column(default=2000)
    credits_used: Mapped[float] = mapped_column(default=0.0)
    per_minute_token_limit: Mapped[int] = mapped_column(default=30000)
    billing_cycle_start: Mapped[datetime] = mapped_column(server_default=func.now())

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]


class Workspace(Base):
    """User-owned container for up to WORKSPACE_MAX_JSONS documents (ADR-0018)."""

    __tablename__ = "workspaces"
    # No index=True on FKs in this feature: each composite UNIQUE leads with
    # the FK column and covers list/duplicate/cascade lookups (ADR-0018).
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_workspaces_user_name"),
        # At most one default workspace per user; keyed on is_default (not
        # name) so provisioning stays idempotent after renames.
        Index(
            "uq_workspaces_user_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    """Tagged JSON inside a workspace; content lives only in its versions."""

    __tablename__ = "json_documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "tag", name="uq_json_documents_ws_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    tag: Mapped[str] = mapped_column(String(100))
    # Historical high-water mark: version numbers are never reused, even
    # after the top version is deleted (requirements DB-06).
    last_version_number: Mapped[int] = mapped_column(default=0, server_default="0")
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
    """Immutable snapshot; version_number is append-only, never renumbered."""

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
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped["JsonDocument"] = relationship(back_populates="versions")
