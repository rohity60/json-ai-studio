"""JSON AI Studio -- FastAPI app factory.

Layered layout (ADR-0013):
    controllers/  HTTP routers (request parsing, error mapping)
    services/     business logic (only layer that touches the store)
    db/           SessionStore interface + in-memory implementation,
                  plus async SQLAlchemy engine for signed-up users
                  (ADR-0015)

All endpoints from openapi/spec.yaml. SSE streaming for /api/chat
(ADR-0004). Fail-fast errors (ADR-0007). Auth: anonymous X-API-Key or
Auth0 bearer token via Depends(get_principal) (ADR-0015).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .controllers import routers
from .db.database import dispose_engine, init_engine
from .logging_config import configure as _configure_logging
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "starting JSON AI Studio API log_level=%s log_to_file=%s log_dir=%s "
        "log_file=%s max_bytes=%d backups=%d auth_enabled=%s",
        settings.log_level,
        settings.log_to_file,
        settings.log_dir,
        settings.log_file_name,
        settings.log_max_bytes,
        settings.log_backup_count,
        settings.auth_enabled,
    )
    logger.debug(
        "initializing database engine (DATABASE_URL set=%s)",
        bool(settings.database_url),
    )
    init_engine()  # no-op when DATABASE_URL unset (anonymous-only mode)
    yield
    logger.debug("disposing database engine")
    await dispose_engine()
    logger.info("JSON AI Studio API shutdown complete")


app = FastAPI(title="JSON AI Studio API", version="0.1.0", lifespan=lifespan)

# CORS -- handle OPTIONS preflight for fetch with X-API-Key / bearer header
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-api-key", "authorization"],
    expose_headers=["Retry-After"],
    max_age=86400,
)

logger = logging.getLogger("json_ai_studio.main")
_configure_logging()

for router in routers:
    app.include_router(router)
