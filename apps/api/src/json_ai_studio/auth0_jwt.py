"""Auth0 access-token verification (ADR-0015).

PyJWT + PyJWKClient with 1h key caching. `verify_token` does blocking
urllib I/O on a JWKS cache miss — callers in async context must wrap it
in `fastapi.concurrency.run_in_threadpool`.
"""

from __future__ import annotations

from typing import Any

import jwt
from jwt import PyJWKClient

from .settings import get_settings

_jwk_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        s = get_settings()
        _jwk_client = PyJWKClient(
            f"https://{s.auth0_domain}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )
    return _jwk_client


def verify_token(token: str) -> dict[str, Any]:
    """Validate an Auth0 RS256 access token; return claims.

    Raises jwt.PyJWTError on any failure (bad signature, wrong audience/
    issuer, expired, opaque token).
    """
    s = get_settings()
    signing_key = _client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=s.auth0_audience,
        issuer=f"https://{s.auth0_domain}/",
    )
