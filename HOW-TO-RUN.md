# How to Run

## Local Development (No Docker)

```bash
# Terminal 1 — API
cd apps/api
uv run uvicorn json_ai_studio.main:app --reload --port 8000

# Terminal 2 — Web
cd apps/web
npm run dev
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

Without any extra setup the app runs **anonymous-only** (shared free quota,
no login). Login/signup needs Postgres + Auth0 below.

## Optional Login (Auth0 + Postgres, ADR-0015)

```bash
# 1. Start Postgres (host port 5433 to avoid clashing with a local install)
docker compose up -d db
#    …or standalone:
# docker run -d --name jsonai-pg -e POSTGRES_USER=json_ai \
#   -e POSTGRES_PASSWORD=json_ai -e POSTGRES_DB=json_ai_studio \
#   -p 5433:5432 postgres:16-alpine

# 2. Run database migrations (Alembic)
cd apps/api
cp .env.example .env      # fill in AUTH0_DOMAIN / AUTH0_AUDIENCE
uv run alembic upgrade head

# 3. Frontend Auth0 config
cd ../web
cp .env.example .env.local   # fill in AUTH0_* (AUTH0_SECRET: openssl rand -hex 32)
```

Auth0 dashboard requirements:
- A **Regular Web Application** with callback URL `<APP_BASE_URL>/auth/callback`
  (e.g. `http://localhost:3002/auth/callback`) and matching logout URL.
- An **API** whose identifier equals `AUTH0_AUDIENCE` — without it access
  tokens are opaque and backend validation fails.

Anonymous users keep working unchanged; when they hit a rate/credit limit
the popup offers "Log in for higher free limits". Logged-in users get their
own DB-persisted monthly quota (see `GET /api/me`).

New schema changes: `uv run alembic revision --autogenerate -m "..."` then
`uv run alembic upgrade head`.

## Docker (Local)

```bash
# Build both services
cd ..
docker build -t json-ai-studio-api apps/api
docker build -t json-ai-studio-web apps/web

# Run API
docker run -d -p 8000:8000 --name json-ai-studio-api \
     -e GOOGLE_AI_STUDIO_API_KEY=YOUR_GOOGLE_AI_STUDIO_API_KEY \
  json-ai-studio-api

# Run Web
docker run -d -p 3001:3000 --name json-ai-studio-web \
     -e NEXT_PUBLIC_API_BASE=http://host.docker.internal:8000/api \
  json-ai-studio-web
```

- Web: `http://localhost:3001`
- API: `http://localhost:8000`

Stop:
```bash
docker stop json-ai-studio-api json-ai-studio-web
docker rm json-ai-studio-api json-ai-studio-web
```

## Docker Compose (Local)

```bash
docker compose up --build
```

- Web: `http://localhost:3001`
- API: `http://localhost:8000`

## Dokploy Deployment

### Service 1: API
- **Dockerfile path**: `apps/api/Dockerfile`
- **Container Port**: `8000`
- **Host Port**: `8000`
- **Env Vars**:
   - `GOOGLE_AI_STUDIO_API_KEY` = your Google AI Studio key
   - `HOST` = `0.0.0.0`
   - `PORT` = `8000`

### Service 2: Web
- **Dockerfile path**: `apps/web/Dockerfile`
- **Container Port**: `3000`
- **Host Port**: `3002` (or any port you choose)
- **Env Vars**:
   - `NEXT_PUBLIC_API_BASE` = `http://localhost:8000/api`
   - `HOST` = `0.0.0.0`
   - `PORT` = `3000`

- Web: `http://localhost:3002`
- API: `http://localhost:8000`

Port mapping is configured in **Dokploy UI** → Service Settings → Ports section. Not in code.

## Dokploy UI Steps

1. Add API service:
   - Dockerfile: `apps/api/Dockerfile`
   - Port: `8000:8000`
   - Env: `GOOGLE_AI_STUDIO_API_KEY`

2. Add Web service:
   - Dockerfile: `apps/web/Dockerfile`
   - Port: `3002:3000`
   - Env: `NEXT_PUBLIC_API_BASE=http://localhost:8000/api`

3. Access: `http://localhost:3002`

## Quick Reference

| Service | Port | URL |
|---------|------|-----|
| Web (dev) | 3000 | http://localhost:3000 |
| Web (docker) | 3001 | http://localhost:3001 |
| Web (dokploy) | 3002 | http://localhost:3002 |
| API (all) | 8000 | http://localhost:8000 |
| API Docs | 8000 | http://localhost:8000/docs |
