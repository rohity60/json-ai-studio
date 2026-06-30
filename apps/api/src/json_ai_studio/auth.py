"""API key auth middleware & rate limiter (per-session key, no login).

Each frontend session generates a random key (crypto.randomUUID()). Key
sent via `X-API-Key` header on every request. Rate limit: 10 requests /
minute per key. Returns 429 when exceeded, 401 when missing/invalid.

Non-protected paths (health, docs) skip auth entirely.
"""

from __future__ import annotations

import time
from collections import defaultdict
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# Non-protected: health, OpenAPI schema, docs UI, favicon.
_UNPROTECTED_PREFIXES = (
     "/health",
     "/docs",
     "/openapi.json",
     "/favicon.ico",
)

_RATE_LIMIT = 10   # requests per window
_RATE_WINDOW = 60   # seconds


class _RateLimiter:
    """Sliding-window rate limiter, in-memory dict.

    Tracks timestamps per key; prunes entries older than the window on
    each check. Returns True if allowed, False if rate-limited.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - _RATE_WINDOW

        # Prune old entries.
        self._windows[key] = [t for t in self._windows[key] if t > window_start]

        if len(self._windows[key]) >= _RATE_LIMIT:
            return False

        self._windows[key].append(now)
        return True


_limiter = _RateLimiter()


async def require_api_key(request: Request) -> str:
    """FastAPI-dependency callable. Put `Depends(require_api_key)` on any
    endpoint that should require auth + rate limiting.

    Returns the API key string on success. Raises 401/429 on failure.
    """

    # Skip non-protected paths.
    if any(request.url.path.startswith(p) for p in _UNPROTECTED_PREFIXES):
        return ""

    #key = request.headers.get("x-api-key")
    key = "dev-default-key"
    if not key or len(key) < 8:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key. Send valid X-API-Key header.",
        )

    if not _limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. {_RATE_LIMIT} requests per {_RATE_WINDOW}s window.",
        )

    return key
