# Login Feature — Task List (Frontend)

**Feature branch:** `login`
**Requirements:** `requirements.md`
**Implementation:** `implementation.md`

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | `npm install @auth0/nextjs-auth0 --legacy-peer-deps`. | done |
| 2 | Add `src/lib/auth0.ts` — `Auth0Client` with audience + scope from env. | done |
| 3 | Add `src/middleware.ts` — `auth0.middleware`; passthrough when Auth0 env unset; matcher excludes static assets. | done |
| 4 | Add `src/lib/authToken.ts` — `getBearerToken()` cache around `getAccessToken()`, exp-aware; `clearBearerToken()`. | done |
| 5 | Modify `src/lib/api.ts` — `authHeaders()` helper on every call incl. `streamChat`; extend `httpError()` (detail/loginAvailable/retryAfter); add `getMe()`. | done |
| 6 | Add `src/components/UserChip.tsx` — `useUser()` login/logout control. | done |
| 7 | Modify `src/app/studio/page.tsx` — render `<UserChip />` in header. | done |
| 8 | Modify `src/components/RateLimitModal.tsx` — `kind`/`loginAvailable`; credits variant; "Log in for higher free limits" button. | done |
| 9 | Modify `src/context/SessionContext.tsx` — handle SSE `credit_limit`; `handleQuotaError` (402/429) in catch blocks; fetch `/api/me` → `profile`; `clearBearerToken()` on logout. | done |
| 10 | Add `.env.example`; add `apps/web/.env.local` to `.gitignore`. | done |
| 11 | Verify: `tsc --noEmit`, `npm run build`, preview studio, burn rate limit → modal + login CTA (screenshot). | done |

---

*Total: 11 tasks. Order 1→11. Requires the backend (`apps/api/ai/feature/login/`) contract to be live for real login testing.*
