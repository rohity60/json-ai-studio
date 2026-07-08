"""Alembic async migration environment (ADR-0015).

URL comes from Settings (DATABASE_URL env var / apps/api/.env), never from
alembic.ini. Async engine + run_sync pattern per SQLAlchemy 2.0 docs.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from json_ai_studio.db.models_orm import Base
from json_ai_studio.settings import get_settings

config = context.config

database_url = get_settings().database_url
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Export it or add it to apps/api/.env, e.g. "
        "postgresql+asyncpg://json_ai:json_ai@localhost:5432/json_ai_studio"
    )
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
