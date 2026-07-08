"""Auth + quota tests (ADR-0015): JWT verification, Principal resolution,
rate limiting, and the anonymous credit pool.

Run from apps/api with `PYTHONPATH=. uv run pytest`.
"""

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.json_ai_studio import auth as auth_mod
from src.json_ai_studio.auth import Principal, get_principal
from src.json_ai_studio.auth0_jwt import verify_token
from src.json_ai_studio.services import credit_service
from src.json_ai_studio.settings import get_settings


def make_request(path: str = "/api/sessions", headers: dict | None = None) -> Request:
    """Build a minimal Starlette Request for dependency-level tests."""
    headers = headers or {}
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": raw,
        "query_string": b"",
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# auth0_jwt.verify_token
# ---------------------------------------------------------------------------


class TestVerifyToken:
    def test_valid_token_returns_claims(self, auth0_mock):
        token = auth0_mock(sub="auth0|abc", email="a@b.com")
        claims = verify_token(token)
        assert claims["sub"] == "auth0|abc"
        assert claims["email"] == "a@b.com"

    def test_expired_token_rejected(self, auth0_mock):
        token = auth0_mock(exp_offset=-10)
        with pytest.raises(jwt.PyJWTError):
            verify_token(token)

    def test_wrong_audience_rejected(self, auth0_mock):
        token = auth0_mock(aud="https://other.api")
        with pytest.raises(jwt.PyJWTError):
            verify_token(token)

    def test_garbage_token_rejected(self, auth0_mock):
        with pytest.raises(jwt.PyJWTError):
            verify_token("not.a.jwt")


# ---------------------------------------------------------------------------
# get_principal — anonymous
# ---------------------------------------------------------------------------


class TestGetPrincipalAnonymous:
    @pytest.mark.asyncio
    async def test_unprotected_path_is_anonymous(self):
        p = await get_principal(make_request(path="/health"))
        assert p.kind == "anonymous"
        assert p.quota_key == ""

    @pytest.mark.asyncio
    async def test_x_api_key_maps_to_shared_pool(self, monkeypatch):
        monkeypatch.setenv("GENERAL_API_KEY", "shared-pool-key")
        get_settings.cache_clear()
        req = make_request(headers={"x-api-key": "browser-key-123456"})
        p = await get_principal(req)
        assert p.kind == "anonymous"
        assert p.quota_key == "shared-pool-key"  # credits pooled
        assert p.rate_key == "browser-key-123456"  # rate per browser
        assert p.login_available is True

    @pytest.mark.asyncio
    async def test_short_api_key_rejected(self, monkeypatch):
        # No header + short general key => too short => 401.
        monkeypatch.setenv("GENERAL_API_KEY", "short")
        get_settings.cache_clear()
        with pytest.raises(HTTPException) as exc:
            await get_principal(make_request(headers={"x-api-key": "tiny"}))
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# get_principal — bearer
# ---------------------------------------------------------------------------


class TestGetPrincipalBearer:
    @pytest.mark.asyncio
    async def test_bearer_without_auth_configured_returns_503(self):
        # No AUTH0_* / DATABASE_URL => auth disabled.
        get_settings.cache_clear()
        req = make_request(headers={"authorization": "Bearer something"})
        with pytest.raises(HTTPException) as exc:
            await get_principal(req)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_invalid_bearer_returns_401(self, auth0_mock):
        req = make_request(headers={"authorization": "Bearer bad.token.here"})
        with pytest.raises(HTTPException) as exc:
            await get_principal(req)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_bearer_provisions_user(self, auth0_mock, monkeypatch):
        import uuid

        from src.json_ai_studio.services import user_service

        fake_id = uuid.uuid4()

        class _User:
            id = fake_id
            email = "u@b.com"

        async def fake_upsert(claims, token):
            return _User()

        monkeypatch.setattr(user_service, "upsert_from_claims", fake_upsert)

        token = auth0_mock(sub="auth0|xyz")
        req = make_request(headers={"authorization": f"Bearer {token}"})
        p = await get_principal(req)
        assert p.kind == "user"
        assert p.quota_key == "user:auth0|xyz"
        assert p.user_id == fake_id
        assert p.login_available is False


# ---------------------------------------------------------------------------
# rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_exceeding_limit_returns_429_with_login_flag(self, monkeypatch):
        monkeypatch.setenv("ANON_REQUESTS_PER_MINUTE", "3")
        monkeypatch.setenv("GENERAL_API_KEY", "pool-key")
        get_settings.cache_clear()
        # Fresh limiter so other tests' timestamps don't count.
        monkeypatch.setattr(auth_mod, "_limiter", auth_mod._RateLimiter())

        headers = {"x-api-key": "same-browser-key-1"}
        for _ in range(3):
            await get_principal(make_request(headers=headers))
        with pytest.raises(HTTPException) as exc:
            await get_principal(make_request(headers=headers))
        assert exc.value.status_code == 429
        assert exc.value.detail["login_available"] is True
        assert exc.value.headers["Retry-After"] == "60"


# ---------------------------------------------------------------------------
# credit_service — anonymous pool
# ---------------------------------------------------------------------------


def _anon(quota_key="pool", rate_key="rk"):
    return Principal(kind="anonymous", quota_key=quota_key, rate_key=rate_key)


class TestCreditServiceAnonymous:
    @pytest.mark.asyncio
    async def test_fresh_pool_passes_check(self):
        await credit_service.check(_anon())  # no raise

    @pytest.mark.asyncio
    async def test_deduct_accumulates(self):
        p = _anon()
        await credit_service.check(p)
        await credit_service.deduct(p, credits=5.0, tokens=100)
        assert credit_service.get_anon_credits("pool")["credits_used"] == 5.0

    @pytest.mark.asyncio
    async def test_monthly_exhaustion_raises_402_login_available(self, monkeypatch):
        monkeypatch.setenv("ANON_MONTHLY_CREDIT_LIMIT", "10")
        get_settings.cache_clear()
        p = _anon()
        await credit_service.deduct(p, credits=10.0)
        with pytest.raises(HTTPException) as exc:
            await credit_service.check(p)
        assert exc.value.status_code == 402
        assert exc.value.detail["login_available"] is True

    @pytest.mark.asyncio
    async def test_per_minute_token_cap_raises_429(self, monkeypatch):
        monkeypatch.setenv("ANON_PER_MINUTE_TOKEN_LIMIT", "500")
        get_settings.cache_clear()
        p = _anon()
        # Deduct records tokens (the bug fix: tokens, not credits).
        await credit_service.deduct(p, credits=1.0, tokens=500)
        with pytest.raises(HTTPException) as exc:
            await credit_service.check(p)
        assert exc.value.status_code == 429
        assert exc.value.detail["retry_after"] == 60
