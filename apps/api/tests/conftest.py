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
