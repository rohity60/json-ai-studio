# 0015-optional-auth0-login-with-postgres-user-quotas

**Date**: 2026-07-08
**Status**: Accepted

## Context

Every visitor shared one hardcoded API key (`"dev-default-key"`) with in-memory credit/rate constraints: 402 when the shared monthly credit pool ran out, 429 on the per-minute token cap. There was no login, no user database, and no upgrade path — when an anonymous user hit a wall, the only advice was "wait". We want signup/login so users can get their own quota, without forcing login on casual users, and without touching the session model (sessions stay in-memory per ADR-0006/0013/0014).

## Decision

**Optional login via Auth0**, with a **PostgreSQL `users` table** managed by **SQLAlchemy 2.0 (async)** and **Alembic** migrations. All configuration comes from env vars (`settings.py`, pydantic-settings).

- **Principal abstraction** (`auth.py`): every protected request resolves to a `Principal`. Anonymous → `quota_key = GENERAL_API_KEY` (shared in-memory pool, pre-login behavior), `rate_key` = the browser's `X-API-Key` (per-browser request fairness). Logged-in → both keys = `user:{auth0_sub}`, quota persisted in Postgres, higher free-tier limits (defaults: 2 000 credits/mo per user, 30 000 tokens/min, 30 req/min vs anonymous 10 000 shared credits/mo, 10 000 tokens/min, 10 req/min).
- **JWT validation**: PyJWT + `PyJWKClient` (JWKS cached 1 h, fetch wrapped in `run_in_threadpool`). Invalid/expired bearer → 401, never a silent downgrade to anonymous (would burn the shared pool and confuse the UI).
- **Provisioning**: idempotent `INSERT … ON CONFLICT (auth0_sub) DO UPDATE` inside the auth dependency — no explicit signup endpoint. Access tokens carry only `sub`; email/name/picture are backfilled once from Auth0 `/userinfo` while the row's email is NULL.
- **Quota seam** (`services/credit_service.py`): `check(principal)` / `deduct(principal, credits, tokens)`. User branch does an atomic `UPDATE users SET credits_used = credits_used + :c`. Per-minute token windows stay in-memory (per-process) for both kinds. This also fixed a bug where the per-minute window accumulated credits but was compared against token limits.
- **Quota errors carry `login_available`**: pre-stream 429/402 become SSE `rate_limit`/`credit_limit` events (never a broken stream); plain-HTTP paths (`/api/explain`) return structured 402/429 details. The frontend popup shows "Log in for higher free limits" when `login_available` is true.
- **Frontend**: `@auth0/nextjs-auth0` v4 — middleware mounts `/auth/*` routes (no collision with the `/api/:path*` rewrite); client caches the access token from `/auth/access-token` and sends `Authorization: Bearer` instead of `X-API-Key` when logged in. `GET /api/me` returns profile + credits.
- **Graceful no-DB mode**: without `DATABASE_URL`/`AUTH0_*`, the API and web app run anonymous-only; bearer requests get 503. `uv run uvicorn` keeps working with zero new infra.
- **LLM calls unchanged**: all invocations keep using shared deployment keys from `deployments.yaml`; per-user LLM keys are out of scope.

Licenses: SQLAlchemy (MIT), Alembic (MIT), asyncpg (Apache-2.0), pydantic-settings (MIT), PyJWT (MIT), cryptography (Apache-2.0/BSD), @auth0/nextjs-auth0 (MIT) — all permissive.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Authlib for JWT validation | BSD-3 but pulls a full OAuth framework for one `jwt.decode` call; PyJWT+PyJWKClient is exactly the needed surface. |
| Flyway for migrations | JVM dependency; recent versions moved features to a paid tier. Alembic is Python-native, MIT, autogenerate-capable. |
| Custom session auth (roll our own login) | Rebuilds what Auth0 provides (MFA, social, password reset); not MVP-worthy. |
| In-memory quotas for logged-in users | Lost on restart — defeats the point of signing up. |
| Explicit `POST /api/users/sync` endpoint | Couples frontend orchestration to provisioning; upsert-in-dependency works for any first request. |
| Mandatory login | Product decision: anonymous flow keeps working; login is the fix offered when limits trip. |

## Consequences

- Postgres becomes a deploy dependency **only for login**; anonymous mode degrades gracefully without it.
- Per-minute token windows and the anonymous credit pool are per-process and reset on restart (accepted; same as before).
- Logged-in `credits_used` persists across restarts (DB).
- `usage_records` (persisting `_usage_history`) is the natural next Alembic migration.
- Auth0 requires an API (audience) configured in the tenant, or access tokens come back opaque and fail validation — documented in `.env.example`.
- Schema changes now go through `uv run alembic revision --autogenerate` + `upgrade head`.
