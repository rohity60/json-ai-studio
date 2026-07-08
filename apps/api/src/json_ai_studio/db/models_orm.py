"""SQLAlchemy ORM models (ADR-0015).

Named models_orm to avoid clashing with the wire-format models.py.
Only signed-up users live in the database; sessions stay in-memory
(ADR-0013/0014). Schema changes go through Alembic migrations under
apps/api/alembic/versions/.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
