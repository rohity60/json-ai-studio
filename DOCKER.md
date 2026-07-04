# Docker / Dokploy Deployment

## Quick start

```bash
# Build and run both services
docker compose up --build

# API   → http://localhost:8000
# Web   → http://localhost:3001
```

## Dokploy UI Setup

Deploy via Dokploy web UI (port 3001):

### 1. API Service
- **Source**: This repo (json-ai-studio)
- **Service type**: Dockerfile
- **Dockerfile path**: `apps/api/Dockerfile`
- **Port mapping**: `8000:8000`
- **Environment variables**:
   - `GOOGLE_AI_STUDIO_API_KEY` = your Google AI Studio key
   - `HOST` = `0.0.0.0`
   - `PORT` = `8000`

### 2. Web Service
- **Source**: This repo (json-ai-studio)
- **Service type**: Dockerfile
- **Dockerfile path**: `apps/web/Dockerfile`
- **Port mapping**: `3001:3000`
- **Environment variables**:
   - `NEXT_PUBLIC_API_BASE` = `http://localhost:8000/api`
   - `HOST` = `0.0.0.0`
   - `PORT` = `3000`

### 3. Access
- Web UI: `http://localhost:3001`
- API docs: `http://localhost:8000/docs`

## Files created

| File | Purpose |
|------|---------|
| `apps/api/Dockerfile` | FastAPI + uv build |
| `apps/api/.dockerignore` | Skip cache/venv |
| `apps/api/uv.lock` | Lockfile for `uv sync --frozen` |
| `apps/web/Dockerfile` | Next.js standalone build |
| `apps/web/.dockerignore` | Skip node_modules |
| `apps/web/next.config.ts` | Added `output: 'standalone'` |
| `apps/web/.env.production` | `NEXT_PUBLIC_API_BASE` for Dokploy |
| `docker-compose.yml` | Both services, one command |
| `DOCKER.md` | This file |

## dokploy-specific notes

- Dokploy auto-detects Next.js and FastAPI projects
- Use the Dockerfile approach for full control
- Set `NEXT_PUBLIC_API_BASE` to point to the API service URL
- For Dokploy's internal networking, use service names instead of `localhost`
- The web app rewrites `/api/*` to the API base in dev mode; in production it uses the env var directly
