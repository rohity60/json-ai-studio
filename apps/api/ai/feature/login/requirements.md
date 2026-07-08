# Backend Requirements — JSON AI Studio Login Feature

Optional Auth0 login + signup, per-user quota persistence (ADR-0015). Only
what the **server / API layer** must implement. Anonymous access stays fully
working; login is the upgrade path offered when a quota limit is hit.

---

## 1. Configuration

| # | Requirement | Priority |
|---|-------------|----------|
| C-01 | All Auth0 + DB config from env vars via `settings.py` (pydantic-settings): `AUTH0_DOMAIN`, `AUTH0_AUDIENCE`, `DATABASE_URL`, `GENERAL_API_KEY`, plus six quota overrides. | MVP |
| C-02 | `Settings.auth_enabled` is true only when `auth0_domain` AND `auth0_audience` AND `database_url` are all set. | MVP |
| C-03 | Graceful degradation: with `auth_enabled` false the API boots and serves anonymous traffic; bearer-token requests get `503`. | MVP |
| C-04 | `get_settings()` is `@lru_cache`d — single Settings instance per process. | MVP |
| C-05 | Licensing must stay permissive: SQLAlchemy/Alembic/pydantic-settings/PyJWT (MIT), asyncpg (Apache-2.0). | MVP |

---

## 2. Database + Migrations

| # | Requirement | Priority |
|---|-------------|----------|
| D-01 | PostgreSQL for signed-up users. Async SQLAlchemy 2.0 engine + asyncpg driver (`db/database.py`). | MVP |
| D-02 | `users` table (`db/models_orm.py`): `id` UUID PK, `auth0_sub` unique-indexed, `email`/`name`/`picture` nullable, `plan`, `monthly_credit_limit`, `credits_used`, `per_minute_token_limit`, `billing_cycle_start`, `created_at`, `last_login_at`. | MVP |
| D-03 | Alembic migrations (`alembic/`, async `env.py`). URL injected from Settings, never hardcoded in `alembic.ini`. Initial migration `0001_create_users`. | MVP |
| D-04 | `init_engine()` runs from the app lifespan; no-op when `DATABASE_URL` unset. `session_factory()` returns `None` in anonymous-only mode. | MVP |
| D-05 | Sessions stay in-memory (ADR-0006/0013/0014) — DB is for users only, NOT session state. | MVP |

---

## 3. Auth0 Token Validation

| # | Requirement | Priority |
|---|-------------|----------|
| A-01 | `auth0_jwt.verify_token()` validates RS256 access tokens against the tenant JWKS (PyJWT + `PyJWKClient`, keys cached 1h). Checks signature, `aud`, `iss`, `exp`. | MVP |
| A-02 | JWKS fetch (blocking urllib) wrapped in `run_in_threadpool` from the async dependency. | MVP |
| A-03 | Invalid/expired bearer → `401`. NEVER silently downgrade to anonymous (would burn shared pool + confuse UI). | MVP |

---

## 4. Principal + Auth Dependency

| # | Requirement | Priority |
|---|-------------|----------|
| P-01 | `get_principal` dependency returns a `Principal(kind, quota_key, rate_key, auth0_sub, user_id, email)`. Alias `require_api_key = get_principal` so gate-only controllers (sessions/versions/uploads/diffs) need no edits. | MVP |
| P-02 | Anonymous: `quota_key = GENERAL_API_KEY` (shared credit pool), `rate_key` = browser `X-API-Key` header (per-browser request fairness). `login_available` = true. | MVP |
| P-03 | User: valid bearer → upsert user → `quota_key = rate_key = "user:{auth0_sub}"`, `login_available` = false. | MVP |
| P-04 | Sliding-window rate limiter keyed on `rate_key`; limit differs by kind (anon 10/min, user 30/min, both overridable). Over limit → `429` with `login_available` + `Retry-After`. | MVP |
| P-05 | Unprotected paths (`/health`, `/docs`, `/openapi.json`, `/favicon.ico`) return an empty anonymous Principal, no auth. | MVP |

---

## 5. User Provisioning

| # | Requirement | Priority |
|---|-------------|----------|
| PR-01 | `user_service.upsert_from_claims()` — idempotent `INSERT ... ON CONFLICT (auth0_sub) DO UPDATE last_login_at`, inside the auth dependency. No explicit signup endpoint. | MVP |
| PR-02 | Access tokens carry only `sub`; email/name/picture backfilled once from Auth0 `/userinfo` (httpx) while the row's email is NULL. | MVP |
| PR-03 | `user_service.get_profile()` applies a 30-day billing-cycle reset (zero `credits_used`, bump `billing_cycle_start`) so `/api/me` never shows stale usage. | MVP |

---

## 6. Quota Refactor

| # | Requirement | Priority |
|---|-------------|----------|
| Q-01 | `credit_service.check(principal)` / `deduct(principal, credits, tokens)` — single seam branching by principal kind. | MVP |
| Q-02 | Anonymous: existing in-memory shared pool (monthly credit check + per-minute token window), limits from Settings. | MVP |
| Q-03 | User: DB read for monthly limit + atomic `UPDATE users SET credits_used = credits_used + :c`; per-minute token window stays in-memory keyed by `quota_key`. | MVP |
| Q-04 | Bug fix: per-minute window records **tokens** (was recording credits while the check summed against a token limit). | MVP |
| Q-05 | `gateway.invoke()`/`explain()` take a `Principal` instead of `api_key`. Pre-stream 429/402 become SSE `rate_limit` / `credit_limit` events (never raise after the stream started). `explain()` keeps HTTP 402/429 with structured detail. | MVP |
| Q-06 | All quota error bodies + SSE events carry `login_available` so the frontend can show the login CTA. | MVP |
| Q-07 | Bug fix: `chat_service` passes the real session id (was hardcoded `"chat-session"`), so usage history is keyed correctly. | MVP |

---

## 7. New Endpoint

| # | Requirement | Priority |
|---|-------------|----------|
| E-01 | `GET /api/me` — bearer only. Returns `UserProfile` (id, email, name, picture, plan, credits{monthly_limit, used, remaining, billing_cycle_start}, per_minute_token_limit). | MVP |
| E-02 | Anonymous caller (X-API-Key only) → `401`. | MVP |
| E-03 | Contract updated first: `openapi/spec.yaml` gains `bearerAuth` scheme, `/api/me` path, `UserProfile`/`CreditsInfo`/`QuotaError` schemas, `Error402`. Then `models.py` mirrors it (ADR-0011 workflow). | MVP |

---

## 8. Excluded from MVP

- Migrating session state to the database (stays in-memory).
- Persisting usage history to a `usage_records` table (natural next migration).
- Per-user LLM API keys (logged-in users still use shared deployment keys).
- Mandatory login / gating the whole app.
- Roles, scopes, teams, org management.
- Refresh-token rotation handling beyond what @auth0/nextjs-auth0 provides.
- Billing / paid plans (only the `free` plan exists).

---

*End of requirements. Feature branch: `login`. Decision record: `docs/adr/0015-optional-auth0-login-with-postgres-user-quotas.md`.*
