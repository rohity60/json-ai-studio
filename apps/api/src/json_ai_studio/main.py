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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()  # no-op when DATABASE_URL unset (anonymous-only mode)
    yield
    await dispose_engine()


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
