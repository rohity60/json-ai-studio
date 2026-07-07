"""JSON AI Studio -- FastAPI app factory.

Layered layout (ADR-0013):
    controllers/  HTTP routers (request parsing, error mapping)
    services/     business logic (only layer that touches the store)
    db/           SessionStore interface + in-memory implementation

All endpoints from openapi/spec.yaml. SSE streaming for /api/chat
(ADR-0004). Fail-fast errors (ADR-0007). Auth: X-API-Key header +
rate limiter (10 req/min per key) via Depends(require_api_key).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .controllers import routers
from .logging_config import configure as _configure_logging

app = FastAPI(title="JSON AI Studio API", version="0.1.0")

# CORS -- handle OPTIONS preflight for fetch with X-API-Key header
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "x-api-key"],
    expose_headers=["Retry-After"],
    max_age=86400,
)

logger = logging.getLogger("json_ai_studio.main")
_configure_logging()

for router in routers:
    app.include_router(router)
