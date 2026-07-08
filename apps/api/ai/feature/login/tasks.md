# Login Feature — Task List (Backend)

**Feature branch:** `login`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Add `settings.py` (pydantic-settings): Auth0 + DATABASE_URL + quota limits, `auth_enabled`, `@lru_cache get_settings()`. Add deps to `pyproject.toml` (sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, pyjwt[crypto], httpx). Add `db` service to `docker-compose.yml`. | done |
| 2 | Add `db/database.py` (async engine + session_factory) and `db/models_orm.py` (`User` table). | done |
| 3 | Scaffold Alembic: `alembic.ini`, async `alembic/env.py`, `script.py.mako`, `versions/0001_create_users.py`. Run `alembic upgrade head`. | done |
| 4 | Add `auth0_jwt.py` (`verify_token`, PyJWKClient cached 1h). | done |
| 5 | Rewrite `auth.py`: `Principal` dataclass + `get_principal` dependency + `_RateLimiter.allow(key, limit)`; keep `require_api_key` alias. | done |
| 6 | Add `services/user_service.py` (`upsert_from_claims` with /userinfo backfill, `get_profile` with cycle reset). | done |
| 7 | Add `services/credit_service.py` (`check`/`deduct` by principal kind; fix per-minute window to record tokens). | done |
| 8 | Refactor `gateway.py`: `invoke`/`explain` take `Principal`; pre-stream 402/429 → SSE `credit_limit`/`rate_limit`. | done |
| 9 | Modify `services/chat_service.py`: thread `Principal` + real session id; forward `credit_limit` event. | done |
| 10 | Add `controllers/users.py` (`GET /api/me`); wire `principal` into `chat.py`/`explain.py`; register in `__init__.py`. | done |
| 11 | Modify `main.py`: lifespan (init/dispose engine) + CORS `authorization` header. | done |
| 12 | Update `openapi/spec.yaml` (bearerAuth, /api/me, QuotaError/UserProfile/CreditsInfo, Error402) then mirror in `models.py`. | done |
| 13 | Add `tests/conftest.py` (`auth0_mock`) + `tests/test_auth.py` (15 tests). Add `pytest-asyncio`. | done |
| 14 | Verify: alembic upgrade, anonymous regression, 503/401/402/429 paths, DB user quota, full pytest + black. | done |

---

*Total: 14 tasks. Order roughly 1→14; spec (12) precedes models per ADR-0011 but was done after the DB/auth core was stable.*
