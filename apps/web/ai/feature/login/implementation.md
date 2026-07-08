# JSON AI Studio — Login Feature Implementation Guide (Frontend)

**Feature branch:** `login`
**Requirements:** `requirements.md`
**Decision record:** `docs/adr/0015-optional-auth0-login-with-postgres-user-quotas.md`

---

## 1. Architecture

```
middleware.ts (auth0.middleware)  → serves /auth/login,/logout,/callback,/access-token
        │
studio/layout.tsx  → SessionProvider
        │
SessionContext  ── getMe() → profile
        │  api.* calls
        ▼
lib/api.ts  → authHeaders(apiKey)
        │        ├─ getBearerToken() (lib/authToken.ts, cached) → Authorization: Bearer
        │        └─ else → X-API-Key
        ▼
FastAPI backend
        │  402/429 → SSE credit_limit/rate_limit OR JSON detail{login_available}
        ▼
handleQuotaError → showRateLimitModal({kind, loginAvailable})
        │
RateLimitModal → "Log in for higher free limits" → /auth/login?returnTo=/studio
```

**Key principle:** logging in is optional and additive. The `authHeaders`
helper is the single switch — bearer when a token exists, X-API-Key
otherwise. Every existing `api.ts` function keeps its `apiKey` argument; the
SSE chat path already uses `fetch` + a stream reader, so an `Authorization`
header attaches cleanly (an `EventSource` could not set headers).

---

## 2. Component Details

### 2.1 `lib/auth0.ts` — New

```ts
import { Auth0Client } from '@auth0/nextjs-auth0/server';
export const auth0 = new Auth0Client({
    authorizationParameters: {
        audience: process.env.AUTH0_AUDIENCE,
        scope: process.env.AUTH0_SCOPE || 'openid profile email',
    },
});
```

### 2.2 `middleware.ts` — New

Calls `auth0.middleware(request)`; short-circuits to `NextResponse.next()`
when `AUTH0_DOMAIN`/`AUTH0_CLIENT_ID` are unset (anonymous-only). Matcher
excludes `_next/static`, `_next/image`, `favicon.ico`, `icon.svg`,
`sitemap.xml`, `robots.txt`.

### 2.3 `lib/authToken.ts` — New

Module-scope `cached = {token, exp}`. `getBearerToken()` returns the cached
token while `exp - 60 > now`, else calls `getAccessToken()` (round-trips to
`/auth/access-token`, refreshing via the session cookie), decodes `exp` from
the payload, caches, returns. Any throw → `null` (anonymous).
`clearBearerToken()` nulls the cache.

### 2.4 `lib/api.ts` — Modify

```ts
async function authHeaders(apiKey: string, extra = {}) {
  const token = await getBearerToken();
  return token
    ? { ...extra, Authorization: `Bearer ${token}` }
    : { ...extra, 'X-API-Key': apiKey };
}
```
Every function (`createSession`, `getSession`, `uploadJson`, `streamChat`,
`explain`, diff/version calls, …) now `await authHeaders(...)` for its
headers. `httpError()` extended: JSON-parse the body → `err.detail`,
`err.loginAvailable = detail.login_available`, and fill `err.retryAfter` from
`detail.retry_after` when the header is absent. New `getMe()` sends bearer to
`/api/me`, returns `null` on anon/failure.

### 2.5 `components/UserChip.tsx` — New

`'use client'`, `useUser()`. `isLoading` → render nothing. No user → "Log in"
link (`/auth/login?returnTo=/studio`). User → avatar (`user.picture`) +
`user.name || user.email` + logout link (`/auth/logout`, `onClick`
`clearBearerToken()`).

### 2.6 `app/studio/page.tsx` — Modify

Import + render `<UserChip />` in the header, after the sidebar-toggle button.

### 2.7 `components/RateLimitModal.tsx` — Modify

`RateLimitInfo` gains `kind?: 'rate' | 'credits'` and `loginAvailable?`.
`isCredits = info.kind === 'credits'` → title "Free credits used up", skip the
countdown paragraph. When `info.loginAvailable`, render a primary "Log in for
higher free limits" button (`window.location.href = '/auth/login?returnTo=/studio'`)
above the "Got it" dismiss button (which turns neutral-gray when the CTA is shown).

### 2.8 `context/SessionContext.tsx` — Modify

- Add `profile` to `SessionState`; `useEffect` on mount calls `api.getMe()` → set `profile` (null when anon).
- `isCreditExhausted(err)` = `err.status === 402`; `handleQuotaError(err)` shows the credits modal (402) or rate modal (429) with `loginAvailable`, returns true when handled.
- SSE loop: `if (chunk.type === 'rate_limit' || chunk.type === 'credit_limit')` → `showRateLimitModal({kind, message, retryAfter: data.retry_after, loginAvailable: data.login_available})` then break.
- Catch blocks of `createSession`/`uploadJson`/`sendMessage`/`explainJson` call `handleQuotaError(err)` before the generic toast.

### 2.9 Env — New

`.env.local` (gitignored) + `.env.example`: `AUTH0_DOMAIN`,
`AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `AUTH0_SECRET` (`openssl rand -hex
32`), `APP_BASE_URL=http://localhost:3002`, `AUTH0_AUDIENCE`,
`AUTH0_SCOPE=openid profile email`, existing `NEXT_PUBLIC_API_BASE`.
`.gitignore` adds `apps/web/.env.local`.

---

## 3. Data Flow

### 3.1 Anonymous → credit wall → login CTA

```
1. streamChat over fetch reader yields {type:'credit_limit', data:{login_available:true}}
2. SessionContext shows credits modal + CTA
3. Click → Auth0 Universal Login → /auth/callback → /studio
4. UserChip shows user; getMe() populates profile
```

### 3.2 Logged-in call

```
1. getBearerToken() → cached JWT (or refresh)
2. authHeaders → Authorization: Bearer
3. Backend quota keyed on user:{sub}
```

---

## 4. Error Handling

| Case | Where | UI |
|------|-------|----|
| SSE `rate_limit` | streamChat loop | rate modal + countdown (+CTA if `login_available`) |
| SSE `credit_limit` | streamChat loop | credits modal (+CTA) |
| HTTP 402 | `handleQuotaError` | credits modal (+CTA) |
| HTTP 429 | `handleQuotaError` | rate modal + countdown (+CTA) |
| 401 / API-key | catch blocks | toast "Auth required / refresh" |
| Not logged in | `getBearerToken` → null | falls back to X-API-Key |

---

## 5. Assumptions & Constraints

1. **Optional.** No route guards; auth checked at API-call time. Anonymous fully works.
2. **fetch, not EventSource.** SSE consumed via `fetch` + reader → bearer header attaches.
3. **Token cache.** Client caches the access token, refreshes near expiry via `/auth/access-token`.
4. **v4 routes at `/auth/*`.** No rewrite collision with `/api/:path*`.
5. **Audience required.** Without an Auth0 API matching `AUTH0_AUDIENCE`, tokens are opaque and the backend rejects them.
6. **Profile fetched, not yet rendered.** `profile` is in context for a future usage meter.

---

## 6. Files Modified / Created

| File | Action | Change |
|------|--------|--------|
| `src/lib/auth0.ts` | **NEW** | Auth0Client |
| `src/middleware.ts` | **NEW** | auth0.middleware + passthrough |
| `src/lib/authToken.ts` | **NEW** | bearer token cache |
| `src/components/UserChip.tsx` | **NEW** | header login/logout |
| `src/lib/api.ts` | **MODIFIED** | authHeaders on all calls, httpError detail, getMe |
| `src/components/RateLimitModal.tsx` | **MODIFIED** | kind/loginAvailable + CTA |
| `src/context/SessionContext.tsx` | **MODIFIED** | credit_limit SSE, handleQuotaError, profile |
| `src/app/studio/page.tsx` | **MODIFIED** | render UserChip |
| `.env.example`, `.gitignore` | **NEW/MODIFIED** | Auth0 env docs |
| `package.json` | **MODIFIED** | add @auth0/nextjs-auth0 |

---

## 7. Verification

1. `npm install @auth0/nextjs-auth0 --legacy-peer-deps`; `npx tsc --noEmit` clean; `npm run build` clean.
2. Studio renders with "Log in" chip in header (anonymous).
3. Burn the request limit → `RateLimitModal` shows countdown + "Log in for higher free limits" (verified via preview: screenshot captured).
4. With Auth0 env set: click Log in → Universal Login → `/studio`; UserChip shows user; `users` row created; `GET /api/me` returns profile.
5. Logout → falls back to anonymous X-API-Key.

---

*End of implementation guide. Feature branch: `login`.*
