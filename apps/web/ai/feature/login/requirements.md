# Frontend Requirements — JSON AI Studio Login Feature

Optional Auth0 login/signup (ADR-0015). Only what the **client / UI layer**
must implement. Anonymous usage stays unchanged; login is offered when a
quota limit trips, and gives the user their own free-tier quota.

---

## 1. Auth0 Wiring

| # | Requirement | Priority |
|---|-------------|----------|
| A-01 | Install `@auth0/nextjs-auth0` v4 (`--legacy-peer-deps`, React 19). | MVP |
| A-02 | `lib/auth0.ts`: `Auth0Client` with `authorizationParameters` (`audience` = `AUTH0_AUDIENCE`, `scope` = `AUTH0_SCOPE` default `openid profile email`). | MVP |
| A-03 | `middleware.ts`: mount `auth0.middleware`, matcher excludes static assets. v4 serves `/auth/login`, `/auth/logout`, `/auth/callback`, `/auth/access-token` — no collision with the `/api/:path*` rewrite. When Auth0 env vars are absent, pass through (anonymous-only mode). | MVP |
| A-04 | Config from env only (`.env.local`, gitignored): `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_SECRET`, `APP_BASE_URL`, `AUTH0_AUDIENCE`, `AUTH0_SCOPE`. Document in `.env.example`. | MVP |

---

## 2. Token Attachment

| # | Requirement | Priority |
|---|-------------|----------|
| T-01 | `lib/authToken.ts`: `getBearerToken()` — module-scope cache around `getAccessToken()`; re-fetch only within 60s of `exp` (decode payload client-side, no verification). Returns `null` when not logged in. `clearBearerToken()` for logout. | MVP |
| T-02 | `lib/api.ts`: `authHeaders(apiKey, extra)` helper — `Authorization: Bearer <token>` when logged in, else `X-API-Key: <apiKey>`. Applied to every backend call including `streamChat` (fetch + reader, so the header attaches — not EventSource). | MVP |
| T-03 | `httpError()` parses the JSON body → `err.detail`, `err.loginAvailable` (`detail.login_available`), and picks up `retry_after` when no `Retry-After` header. So 402/429 metadata reaches callers. | MVP |
| T-04 | `getMe()` client → `GET /api/me` with bearer; returns `null` when anonymous or no user DB. | MVP |

---

## 3. UI

| # | Requirement | Priority |
|---|-------------|----------|
| U-01 | `UserChip.tsx` (uses `useUser()`): logged out → "Log in" link to `/auth/login?returnTo=/studio`; logged in → avatar + name/email + logout link to `/auth/logout` (calls `clearBearerToken()`). | MVP |
| U-02 | Render `<UserChip />` in the studio header (`app/studio/page.tsx`), next to the sidebar toggle. | MVP |
| U-03 | `RateLimitModal` gains `kind: 'rate' \| 'credits'` and `loginAvailable`. Credits variant: title "Free credits used up", no countdown. When `loginAvailable`, a primary "Log in for higher free limits" button → `/auth/login?returnTo=/studio` above the dismiss button. | MVP |

---

## 4. Quota-Error Handling

| # | Requirement | Priority |
|---|-------------|----------|
| Q-01 | `SessionContext`: SSE loop handles `credit_limit` alongside `rate_limit`; passes `data.login_available` into `showRateLimitModal`. | MVP |
| Q-02 | Shared `handleQuotaError(err)` in catch blocks of `sendMessage`/`uploadJson`/`createSession`/`explainJson`: `402` → credits modal, `429` → rate modal, both with `loginAvailable` from the parsed error. Returns true when it handled the error. | MVP |
| Q-03 | On mount, fetch `GET /api/me` and expose `profile` in context (null when anonymous). Call `clearBearerToken()` on logout. | MVP |

---

## 5. Data Flow

### 5.1 Anonymous hits a limit

```
1. User (X-API-Key) chats until per-minute cap trips
2. Backend streams SSE credit_limit / rate_limit {login_available: true}
3. SessionContext → showRateLimitModal({kind, loginAvailable: true})
4. Modal shows message + "Log in for higher free limits" button
5. Click → /auth/login?returnTo=/studio → Auth0 Universal Login
```

### 5.2 Logged-in request

```
1. getBearerToken() returns cached/refreshed access token
2. authHeaders() sends Authorization: Bearer instead of X-API-Key
3. Backend keys quota on user:{sub}; higher free-tier limits apply
4. UserChip shows avatar + name; GET /api/me populates profile
```

### 5.3 No Auth0 configured (local dev)

```
1. middleware.ts passes through; getAccessToken() throws → null
2. All calls fall back to X-API-Key; UserChip shows "Log in" (which 404s
   until env is set) — app fully usable anonymously
```

---

## 6. Excluded from MVP

- Protecting routes at the edge (all pages stay public; auth checked at call time).
- Per-user LLM model/key selection.
- Showing live credit balance / usage meter in the UI (profile is fetched but not yet rendered).
- Account settings / profile edit page.
- Social-login provider buttons in-app (handled by Auth0 Universal Login).
- Remember-me / silent re-auth beyond the SDK default.

---

*End of requirements. Feature branch: `login`. Backend contract: `apps/api/ai/feature/login/`.*
