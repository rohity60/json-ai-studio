"""Shared fixtures for the auth/quota tests (ADR-0015).

The Auth0 fixture mints RS256 tokens with a throwaway keypair and points
the JWKS lookup at that key, so `verify_token` runs its real
signature/audience/issuer/expiry checks with no network and no live tenant.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.json_ai_studio import auth0_jwt
from src.json_ai_studio.services import credit_service
from src.json_ai_studio.settings import get_settings

_DOMAIN = "mock.test"
_AUDIENCE = "https://api.test"
_ISSUER = f"https://{_DOMAIN}/"


@pytest.fixture
def auth0_mock(monkeypatch):
    """Configure a fake Auth0 tenant + return a token-minting helper.

    Sets AUTH0_DOMAIN/AUTH0_AUDIENCE/DATABASE_URL so `settings.auth_enabled`
    is true, patches the JWKS client to hand back our public key, and yields
    a `mint(sub=..., **claims)` function producing valid RS256 tokens.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    monkeypatch.setenv("AUTH0_DOMAIN", _DOMAIN)
    monkeypatch.setenv("AUTH0_AUDIENCE", _AUDIENCE)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@localhost/z")
    get_settings.cache_clear()

    class _SigningKey:
        def __init__(self, public_key):
            self.key = public_key

    class _FakeJWKClient:
        def get_signing_key_from_jwt(self, token):
            return _SigningKey(key.public_key())

    monkeypatch.setattr(auth0_jwt, "_client", lambda: _FakeJWKClient())

    def mint(sub: str = "auth0|test-user", exp_offset: int = 3600, **claims) -> str:
        payload = {
            "sub": sub,
            "aud": _AUDIENCE,
            "iss": _ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + exp_offset,
            **claims,
        }
        return jwt.encode(payload, key, algorithm="RS256")

    yield mint

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_quota_state():
    """Reset the in-memory anonymous credit pool between tests."""
    credit_service._anon_credits.clear()
    credit_service._per_minute_tokens.clear()
    yield
    credit_service._anon_credits.clear()
    credit_service._per_minute_tokens.clear()


@pytest.fixture(autouse=True)
def clean_settings_cache():
    """Ensure each test starts with fresh (unconfigured) settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Workspace DB fixtures (ADR-0018)
#
# Integration tests run against a dedicated Postgres database so JSONB, the
# partial unique index, and FOR UPDATE behave exactly as in production. The
# DB is never the dev database — see WS_TEST_DB_URL.
#
# Fixtures are async so the engine is created in the SAME event loop as the
# test (asyncpg connections are loop-bound; a cross-loop engine errors).
# ---------------------------------------------------------------------------

import uuid as _uuid

import pytest_asyncio

WS_TEST_DB_URL = (
    "postgresql+asyncpg://json_ai:json_ai@localhost:5433/json_ai_studio_test"
)


@pytest_asyncio.fixture
async def ws_db():
    """Fresh schema on the test DB, engine wired into the app singletons.

    Drops + recreates all tables each test (clean slate, loop-safe), points
    `db.database` at this engine so the service layer uses it, and re-asserts
    DATABASE_URL so `get_settings()` (cache cleared each test) still resolves
    to the test database.
    """
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.json_ai_studio.db import database as db_mod
    from src.json_ai_studio.db.models_orm import Base

    os.environ["DATABASE_URL"] = WS_TEST_DB_URL
    get_settings.cache_clear()

    engine = create_async_engine(WS_TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    prev_engine, prev_factory = db_mod._engine, db_mod._session_factory
    db_mod._engine = engine
    db_mod._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    yield engine

    db_mod._engine, db_mod._session_factory = prev_engine, prev_factory
    await engine.dispose()


async def _make_user(engine, email: str) -> _uuid.UUID:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.json_ai_studio.db.models_orm import User

    uid = _uuid.uuid4()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(User(id=uid, auth0_sub=f"test|{uid}", email=email))
        await db.commit()
    return uid


@pytest_asyncio.fixture
async def user_id(ws_db):
    """Insert a user row and return its id (workspaces need a real FK)."""
    return await _make_user(ws_db, "u@test.com")


@pytest_asyncio.fixture
async def other_user_id(ws_db):
    """A second user, for cross-tenant isolation tests."""
    return await _make_user(ws_db, "o@test.com")
