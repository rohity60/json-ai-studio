# 0017-logging-and-log-rotation

**Date**: 2026-07-11
**Status**: Accepted

## Context

Logging was minimal: a hardcoded `dictConfig` in `logging_config.py` with a single `StreamHandler` → `stderr`, level `INFO`, and only a handful of modules logging (all at INFO/WARNING/ERROR — no DEBUG anywhere). Two gaps hurt operability:

- **No persistence.** Under docker-compose nothing was mounted for logs, so container output vanished on restart; locally logs only scrolled past the terminal. Diagnosing a past request meant it was already gone.
- **No verbose/debug path.** There was no way to see the full working JSON, the LLM prompt/response, or per-diff detail when debugging a bad AI edit.

We also hit a recurring confusion: the Next.js frontend's `console.log` calls live in `"use client"` components, so they print to the **browser** devtools, not the server terminal — which read as "no logs" to operators watching the terminal.

## Decision

**API (Python) only.** File logging + rotation + new INFO/DEBUG logs apply to the FastAPI backend. Frontend logging is explicitly out of scope: browser client logs cannot write server files without a network round-trip, and the backend's file logs are the source of truth for server-side events. (Next.js server stdout is still captured by `docker logs`.)

**Env-driven via `Settings` (ADR-0015 seam).** New `LOG_*` fields on `Settings` (level, dir, file name, file/console toggles, rotation size + backup count, uvicorn capture) — same env-var/default/`@lru_cache` pattern as the auth/quota knobs. No ad-hoc `os.environ` parsing. `log_level` is normalized (uppercased; empty compose passthrough → `INFO`).

**`logging_config.py` builds the `dictConfig` dynamically** from `Settings` (still idempotent, `disable_existing_loggers=False`). Two sinks:

- **console** — `StreamHandler` → stderr (kept so `docker logs` still works).
- **file** — `logging.handlers.RotatingFileHandler`, **size-based** rotation (`maxBytes` × `backupCount`, `app.log.1..N`), UTF-8. `configure()` `mkdir`s the log dir first (the handler does not create parents).

**Plain text format**, enriched with `filename:lineno` for traceability. No new dependency (stdlib only); JSON/structured logging was declined for now.

**Uvicorn capture**: when `log_capture_uvicorn` (default on), the `uvicorn`, `uvicorn.error`, and `uvicorn.access` loggers are re-declared onto the same handlers so request access lines land in the file too. `configure()` runs at app-module import (after uvicorn installs its defaults), so this override sticks.

**Verbose INFO + full-payload DEBUG** across controllers, services, db, auth, gateway, providers, deployment. INFO = one-line summaries (ids, counts, sizes, principal kind); DEBUG = full payloads (working JSON, system prompt, raw LLM output, parsed/applied diffs, session dicts). The stray `print()` in `deployment.py` became `logger.exception`.

**Security rule (overrides "full payloads")**: secrets are never logged. A `mask_secret()` helper (in `auth.py`) redacts API keys / the shared pool key to `...<last4> (len=N)`; bearer tokens are never passed to it — they are simply not logged. `user_service` logs Auth0 **claims** (`sub`/`email`), never the raw token. Provider classes log `base_url` and `api_key_present=bool`, never the key.

**Deploy wiring**: docker-compose api service gets `LOG_*` env (with `${VAR:-default}`) and a bind mount `./logs/api:/app/logs` so files are host-readable and survive restarts; the Dockerfile sets `LOG_DIR=/app/logs` and pre-creates it. `.gitignore` excludes `logs/` and `*.log*`.

### Alternatives Considered

| Approach | Why Not Chosen |
|----------|----------------|
| Time-based rotation (`TimedRotatingFileHandler`, daily) | Size-based bounds disk regardless of traffic and needs no date-correlation tooling; better fit for containers. |
| JSON / structured logs (`python-json-logger`, structlog) | Adds a dependency and hurts raw readability; the MVP has no log aggregator yet. Revisit when shipping to ELK/Loki/Datadog. |
| Ship browser logs to a `POST /api/logs` file sink | Adds an endpoint + auth/rate handling + network chatter for little MVP value; frontend logging deferred entirely. |
| Rely only on `docker logs` / stdout | No local persistence, no rotation, lost on restart — the exact gap this ADR closes. |

## Consequences

- Logs persist locally (`apps/api/logs/app.log`) and in deploys (`./logs/api/app.log` on the host), rotating by size.
- `LOG_LEVEL=DEBUG` yields deep, full-payload traces for debugging AI edits; default `INFO` stays operationally quiet. DEBUG is verbose and may be large — intended for troubleshooting, not steady-state.
- **Not multi-process safe.** `RotatingFileHandler` can race on rollover across multiple uvicorn workers or the `--reload` reloader subprocess. Acceptable for this single-worker MVP; scaling workers should move to a `QueueHandler`/socket sink or external log shipping.
- Secrets stay out of logs by construction (masking + claims-only + never logging tokens).
