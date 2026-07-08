# JSON AI Studio — Login Feature Implementation Guide (Backend)

**Feature branch:** `login`
**Requirements:** `requirements.md`
**Decision record:** `docs/adr/0015-optional-auth0-login-with-postgres-user-quotas.md`

---

## 1. Architecture

```
Request
  → get_principal (auth.py)
      ├─ Authorization: Bearer <jwt>
      │    → verify_token (auth0_jwt.py)  [RS256 vs JWKS, run_in_threadpool]
      │    → user_service.upsert_from_claims  [INSERT ... ON CONFLICT]
      │    → Principal(kind="user", quota_key="user:{sub}")
      └─ X-API-Key <key> (or none)
           → Principal(kind="anonymous", quota_key=GENERAL_API_KEY,
                       rate_key=<browser key>)
  → sliding-window rate limit on rate_key → 429 if exceeded
  → controller → gateway.invoke/explain(principal, ...)
       → credit_service.check(principal)   [402 credits / 429 tokens]
       → LLM stream
       → credit_service.deduct(principal, credits, tokens)
```

**Key principle:** the `Principal` is the single abstraction that lets every
existing controller stay unchanged. Anonymous behavior is byte-for-byte the
pre-login flow (shared pool); logged-in users get a DB-backed quota. The LLM
call is untouched — deployment keys still come from `deployments.yaml`.

---

## 2. Component Details

### 2.1 `settings.py` — New (pydantic-settings)

**Location:** `apps/api/src/json_ai_studio/settings.py`

`Settings(BaseSettings)` with `general_api_key`, `database_url`,
`auth0_domain`, `auth0_audience`, six quota fields, `auth_enabled` property,
`@lru_cache get_settings()`. `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`.

### 2.2 `db/database.py` — New (async engine)

Lazy singleton. `init_engine()` (called from lifespan) builds
`create_async_engine(url, pool_pre_ping=True)` + `async_sessionmaker`.
`session_factory()` returns `None` when `DATABASE_URL` unset (anonymous-only
mode). `dispose_engine()` on shutdown.

### 2.3 `db/models_orm.py` — New (ORM)

`Base(DeclarativeBase)` + `User` mapped class. Named `models_orm` to avoid
clashing with the wire-format `models.py`.

### 2.4 `alembic/` — New (migrations)

- `alembic.ini`: `script_location = alembic`, `prepend_sys_path = src`, blank `sqlalchemy.url`.
- `alembic/env.py`: async pattern — `async_engine_from_config` + `connection.run_sync(do_run_migrations)`. URL set from `get_settings().database_url`; raises if unset.
- `alembic/versions/0001_create_users.py`: hand-written `create_table("users")` + unique index on `auth0_sub`.

Run: `cd apps/api && DATABASE_URL=... uv run alembic upgrade head`.

### 2.5 `auth0_jwt.py` — New (JWT verification)

```python
_jwk_client: PyJWKClient | None = None

def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        s = get_settings()
        _jwk_client = PyJWKClient(
            f"https://{s.auth0_domain}/.well-known/jwks.json",
            cache_keys=True, lifespan=3600)
    return _jwk_client

def verify_token(token: str) -> dict:
    s = get_settings()
    key = _client().get_signing_key_from_jwt(token)   # blocking on cache miss
    return jwt.decode(token, key.key, algorithms=["RS256"],
                      audience=s.auth0_audience, issuer=f"https://{s.auth0_domain}/")
```

### 2.6 `auth.py` — Rewrite (Principal + get_principal)

`@dataclass Principal(kind, quota_key, rate_key, auth0_sub, user_id, email)`
with `login_available` property (`kind == "anonymous"`).

`get_principal(request)`:
1. Unprotected path → empty anonymous Principal.
2. `Authorization: Bearer` → if `not auth_enabled` raise 503; else `verify_token` via `run_in_threadpool` (401 on `PyJWTError`), `user_service.upsert_from_claims`, build user Principal, limit = `user_requests_per_minute`.
3. Else → `client_key = X-API-Key or GENERAL_API_KEY`; if `len < 8` raise 401; anonymous Principal, limit = `anon_requests_per_minute`.
4. `_limiter.allow(rate_key, limit)` → 429 (detail dict with `login_available` + `retry_after`, `Retry-After` header) if exceeded.

`_RateLimiter.allow(key, limit)` — sliding 60s window. `require_api_key = get_principal` (alias).

### 2.7 `services/user_service.py` — New

`upsert_from_claims(claims, token)`: `pg_insert(User).values(...).on_conflict_do_update(index_elements=["auth0_sub"], set_={"last_login_at": now}).returning(User)`; if returned email is NULL, GET `/userinfo` with the bearer token (httpx) and backfill.
`get_profile(user_id)`: select user, apply 30-day cycle reset, return profile dict.
`_require_db()`: raises 503 when `session_factory()` is None.

### 2.8 `services/credit_service.py` — New (quota seam)

`check(principal)`:
- User: DB select → cycle reset → compare `credits_used` vs `monthly_credit_limit` (402) → per-minute token window vs `per_minute_token_limit` (429).
- Anonymous: in-memory `_anon_credits[quota_key]` monthly check (402) + per-minute token window (429), limits from Settings.

`deduct(principal, credits, tokens)`:
- User: atomic `UPDATE users SET credits_used = credits_used + :c`.
- Anonymous: mutate in-memory record.
- Both append `(monotonic_now, tokens)` to `_per_minute_tokens[quota_key]` — **the bug fix** (tokens, not credits).

402/429 raised as `HTTPException` with structured `detail` (`error`, `hint`, `login_available`, `retry_after`).

### 2.9 `gateway.py` — Refactor

`invoke()`/`explain()` signature `api_key: str` → `principal: Principal`.
Replaced `_ensure/_check/_deduct_credits` + all `dev-default-key` special
cases with `credit_service.check/deduct`. `_quota_sse_event(exc)` converts a
pre-stream 402/429 into a `credit_limit`/`rate_limit` SSE event. Usage log
keyed by `principal.quota_key`.

### 2.10 `services/chat_service.py` — Modify

Thread `Principal` through `chat_event_stream` → `_stream_llm` →
`GatewayService.invoke`. Pass the **real** `session["id"]` (was `"chat-session"`).
Forward the new `credit_limit` event exactly like `rate_limit` (stop before `complete`).

### 2.11 `controllers/` — Modify

- `chat.py`, `explain.py`: `principal: Principal = Depends(get_principal)`, passed onward.
- `users.py` (new): `GET /api/me`, 401 for anonymous, `response_model=UserProfile`.
- `__init__.py`: register `users.router`.

### 2.12 `main.py` — Modify

Add `lifespan` (init/dispose engine). Add `"authorization"` to CORS `allow_headers`.

### 2.13 `models.py` + `openapi/spec.yaml` — Modify

Spec first: `bearerAuth` scheme, `security: [{simpleApiKey: []}, {bearerAuth: []}]` on protected ops, `/api/me` path, `QuotaError`/`CreditsInfo`/`UserProfile` schemas, `Error402`, documented SSE `credit_limit` event. Then `models.py` mirrors: `QuotaErrorDetail`, `CreditsInfo`, `UserProfile`.

---

## 3. Data Flow

### 3.1 Anonymous hits credit wall (SSE)

```
1. POST /api/chat, X-API-Key only, shared pool exhausted
2. gateway.invoke → credit_service.check → 402
3. Caught pre-stream → SSE "credit_limit" {login_available: true}
4. chat_service forwards event, stops before "complete"
```

### 3.2 Logged-in request

```
1. POST /api/chat, Authorization: Bearer <jwt>
2. verify_token OK → upsert_from_claims → Principal(user)
3. credit_service.check → DB row within limits
4. LLM stream → credit_service.deduct → UPDATE users.credits_used
```

### 3.3 Bearer with no DB configured

```
1. Any protected path, Authorization: Bearer <jwt>
2. settings.auth_enabled == false → 503
```

---

## 4. Error Handling

| Error | When | Response |
|-------|------|----------|
| `401` | Missing/short X-API-Key; invalid/expired bearer; anonymous on `/api/me` | `{"detail": "..."}` |
| `402` | Monthly credits exhausted | `QuotaError` detail (`login_available`) or SSE `credit_limit` |
| `429` | Request-rate or per-minute token cap | `QuotaError` detail + `Retry-After`, or SSE `rate_limit` |
| `503` | Bearer sent but `auth_enabled` false | `{"detail": "Login is temporarily unavailable..."}` |

---

## 5. Assumptions & Constraints

1. **Optional login.** Anonymous flow unchanged; login is the offered fix at a limit.
2. **Sessions stay in-memory.** DB is users-only (ADR-0013/0014 preserved).
3. **Per-process windows.** Per-minute token windows + anonymous pool reset on restart; user credits persist (DB).
4. **Shared LLM keys.** Logged-in users still use deployment keys; no per-user keys.
5. **Audience required.** `AUTH0_AUDIENCE` must match an Auth0 API or tokens are opaque and fail validation.
6. **No silent downgrade.** Bad bearer → 401, not anonymous.

---

## 6. Files Modified / Created

| File | Action | Change |
|------|--------|--------|
| `settings.py` | **NEW** | pydantic-settings config |
| `db/database.py` | **NEW** | async engine + session factory |
| `db/models_orm.py` | **NEW** | `User` ORM model |
| `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_create_users.py` | **NEW** | migrations |
| `auth0_jwt.py` | **NEW** | RS256 JWKS verification |
| `services/user_service.py` | **NEW** | upsert + profile |
| `services/credit_service.py` | **NEW** | principal-aware quota seam |
| `controllers/users.py` | **NEW** | `GET /api/me` |
| `auth.py` | **MODIFIED** | Principal + get_principal + limiter |
| `gateway.py` | **MODIFIED** | Principal signatures, SSE quota events |
| `services/chat_service.py` | **MODIFIED** | thread principal + real session id |
| `controllers/chat.py`, `controllers/explain.py`, `controllers/__init__.py` | **MODIFIED** | principal wiring, register users router |
| `main.py` | **MODIFIED** | lifespan + CORS authorization header |
| `models.py` | **MODIFIED** | UserProfile / CreditsInfo / QuotaErrorDetail |
| `openapi/spec.yaml` | **MODIFIED** | bearerAuth, /api/me, quota schemas |
| `pyproject.toml`, `docker-compose.yml`, `.env.example` | **MODIFIED/NEW** | deps, db service, env docs |

---

## 7. Verification

### Automated
- `tests/test_auth.py` (15 tests) + `tests/conftest.py`: `auth0_mock` mints RS256 tokens against a throwaway keypair, patches JWKS lookup → real `verify_token` runs. Covers token validation, Principal resolution (anon/bearer/503/401), rate limiter, anonymous credit pool + per-minute token cap. Run: `cd apps/api && PYTHONPATH=. uv run pytest`.

### Manual
1. `docker compose up -d db` → `uv run alembic upgrade head` → `\d users`.
2. API without `DATABASE_URL` → anonymous chat works; bearer → 503.
3. Anonymous regression: upload, chat, accept diff, versions, explain via X-API-Key.
4. Trip per-minute cap → SSE `rate_limit` with `login_available`.
5. Set a user's `monthly_credit_limit=0` in psql → chat yields SSE `credit_limit`; `/api/explain` → HTTP 402.
6. Garbage bearer → 401. API restart → user `credits_used` persists; anon pool resets.

---

*End of implementation guide. Feature branch: `login`.*
