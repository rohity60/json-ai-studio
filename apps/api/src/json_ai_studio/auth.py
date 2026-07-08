"""Auth middleware: optional Auth0 login on top of anonymous API-key access.

Two kinds of principal (ADR-0015):
  anonymous — no Authorization header. Quota is the shared GENERAL_API_KEY
              pool; request-rate is keyed on the browser's X-API-Key so one
              tab cannot starve others.
  user      — valid Auth0 bearer token (RS256, verified against tenant
              JWKS). Provisioned/updated in Postgres on every request via
              upsert. Quota + rate keyed per user.

Invalid/expired bearer tokens get 401 rather than silently downgrading to
anonymous — a silent downgrade would burn the shared pool and confuse the
frontend about who is logged in.

Rate limit: sliding window per rate_key, limit differs by principal kind.
Returns 429 (with login_available flag) when exceeded.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .auth0_jwt import verify_token
from .settings import get_settings

# Non-protected: health, OpenAPI schema, docs UI, favicon.
_UNPROTECTED_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/favicon.ico",
)

_RATE_WINDOW = 60  # seconds


@dataclass
class Principal:
    """Resolved caller identity for quota + rate limiting."""

    kind: Literal["user", "anonymous"]
    quota_key: str  # credit pool key: "user:{auth0_sub}" or GENERAL_API_KEY
    rate_key: str  # request-rate key: per-browser X-API-Key or "user:{sub}"
    auth0_sub: str | None = None
    user_id: uuid.UUID | None = None
    email: str | None = None

    @property
    def login_available(self) -> bool:
        """True when logging in would raise this caller's limits."""
        return self.kind == "anonymous"


class _RateLimiter:
    """Sliding-window rate limiter, in-memory dict.

    Tracks timestamps per key; prunes entries older than the window on
    each check. Returns True if allowed, False if rate-limited.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        window_start = now - _RATE_WINDOW

        # Prune old entries.
        self._windows[key] = [t for t in self._windows[key] if t > window_start]

        if len(self._windows[key]) >= limit:
            return False

        self._windows[key].append(now)
        return True


_limiter = _RateLimiter()


async def get_principal(request: Request) -> Principal:
    """FastAPI-dependency callable. Put `Depends(get_principal)` on any
    endpoint that should require auth + rate limiting.

    Returns a Principal on success. Raises 401/429/503 on failure.
    """

    # Skip non-protected paths.
    if any(request.url.path.startswith(p) for p in _UNPROTECTED_PREFIXES):
        return Principal(kind="anonymous", quota_key="", rate_key="")

    settings = get_settings()
    authorization = request.headers.get("authorization", "")

    if authorization.lower().startswith("bearer "):
        if not settings.auth_enabled:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Login is temporarily unavailable "
                    "(auth/database not configured)."
                ),
            )
        token = authorization[7:]
        try:
            # JWKS fetch on cache miss is blocking urllib I/O.
            claims = await run_in_threadpool(verify_token, token)
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token. Please log in again.",
            )
        from .services import user_service

        user = await user_service.upsert_from_claims(claims, token)
        principal = Principal(
            kind="user",
            quota_key=f"user:{claims['sub']}",
            rate_key=f"user:{claims['sub']}",
            auth0_sub=claims["sub"],
            user_id=user.id,
            email=user.email,
        )
        limit = settings.user_requests_per_minute
    else:
        client_key = request.headers.get("x-api-key") or settings.general_api_key
        if len(client_key) < 8:
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid API key. Send valid X-API-Key header.",
            )
        principal = Principal(
            kind="anonymous",
            quota_key=settings.general_api_key,
            rate_key=client_key,
        )
        limit = settings.anon_requests_per_minute

    if not _limiter.allow(principal.rate_key, limit):
        raise HTTPException(
            status_code=429,
            detail={
                "error": (
                    f"Rate limit reached: {limit} requests per "
                    f"{_RATE_WINDOW}s. Please try again in a moment."
                ),
                "login_available": principal.login_available,
                "retry_after": _RATE_WINDOW,
            },
            headers={"Retry-After": str(_RATE_WINDOW)},
        )

    return principal


# Backwards-compatible alias: gate-only controllers (sessions, versions,
# uploads, diffs) keep `Depends(require_api_key)` unchanged.
require_api_key = get_principal
