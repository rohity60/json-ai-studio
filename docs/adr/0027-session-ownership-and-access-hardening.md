# 0027-session-ownership-and-access-hardening

**Date**: 2026-11-13
**Status**: Proposed

## Context

Sessions live in memory (ADR-0006/0013) and were reachable by any caller holding a valid credential and the session id. Login is optional (ADR-0015): anonymous browsers send a per-browser `X-API-Key`, logged-in users an Auth0 bearer token. Users also log in mid-session and expect to keep their work. Separately, INFO logs carried user email addresses, against the intent of ADR-0017.

## Decision

1. **Every session records an owner** at creation (`POST /sessions`, `/sessions/from-template`, uploads that start a session): `user:{sub}` for a bearer caller, and for an anonymous caller `key:` + SHA-256 of its `X-API-Key`. A digest rather than the key itself, because session dicts are returned to clients and logged at DEBUG; the `owner` field is also stripped from every session response (`public_session`).

2. **Owner-only access, 404 on mismatch.** `controllers/access.py` provides `require_session_owner`, a dependency used on every `/api/sessions/{session_id}/**` route (session, chat clear, versions, diffs, jobs). `/api/chat` and `/api/explain` call `session_service.get_owned_session`. A foreign session answers exactly like an unknown one (`404 Session not found`), so ids cannot be probed. `/api/json/upload` treats a foreign `session_id` like an unknown one and stores the upload in a new session owned by the caller, again with no difference in the answer.

3. **Claim on login.** A bearer caller that also sends the `X-API-Key` that created an anonymous session takes it over: the owner becomes `user:{sub}`. A bearer alone, or a bearer with another key, gets 404. Sessions created without an `X-API-Key` (the shared `GENERAL_API_KEY` fallback) cannot be claimed. The web client now sends its browser key alongside the bearer on every session call, so login mid-session is seamless. After logout the browser key no longer owns the session; the client's existing 404 path restores the IndexedDB copy into a new anonymous session (ADR-0014).

4. **Support access** through an optional `ADMIN_API_KEY` setting: a matching `X-Admin-Key` header (compared in constant time, sent with the normal credentials) opens any session. Each use is logged at WARNING with the session id; a wrong admin key is logged too. Unset (default) disables it.

5. **Emails are masked in logs** by `mask_email()` beside `mask_secret()` in `auth.py` (`r***@g***.com`). `sub` and `user_id` stay; the user upsert debug line logs only whether a name is present, since Auth0 often sets the name to the email.

6. **Edge filtering of scanner traffic** (requests for common secrets/config paths) is a Cloudflare WAF custom rule configured in the dashboard, not code. Those paths already 404 at the origin; the rule only keeps them out of the logs.

## Consequences

- Sharing a session id no longer shares the session; sharing needs a future explicit feature.
- A user who logs out loses server access to sessions they claimed; the browser cache restores the work into a fresh anonymous session.
- Clients that call the API without `X-API-Key` share the general-key owner; the web app always sends one.
- The `SessionStore.create_session` interface gains `owner`; a DB-backed store must persist it.

## References

- ADR-0006, ADR-0013 (session store), ADR-0014 (IndexedDB restore), ADR-0015 (auth), ADR-0017 (logging), ADR-0026 (jobs)
- `apps/api/src/json_ai_studio/auth.py`, `controllers/access.py`, `services/session_service.py`
