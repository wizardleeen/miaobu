# Miaobu - Static & Python Deployment Platform

## Project Overview
Miaobu is a Vercel-like deployment platform that deploys GitHub repositories to Aliyun cloud infrastructure. It supports static sites (Node.js build) and Python web apps (FastAPI/Flask/Django).

## Architecture

### Services (docker-compose)
- **backend** (port 8000): FastAPI API server
- **worker**: Celery async worker (has Docker socket access for Python builds)
- **frontend** (port 3000): React + Vite + TypeScript UI
- **postgres** (port 5433): PostgreSQL 16 database
- **redis** (port 6379): Redis (Celery broker)

### Traffic Routing (ESA-only architecture)
ALL traffic routes through Aliyun ESA (Edge Security Acceleration):
```
*.metavm.tech  →  ESA  →  Edge Routine  →  KV lookup  →  OSS (static) or FC (Python)
custom domains →  ESA  →  Edge Routine  →  KV lookup  →  OSS (static) or FC (Python)
```
- **Edge Routine** (`edge-routine.js`): ES Module format, uses `new EdgeKV({ namespace: "miaobu" })` for routing decisions
- **Static sites**: Edge Routine rewrites URL path (keeps same host for ESA caching), ESA fetches from OSS origin
- **Python apps**: Edge Routine proxies directly to Function Compute endpoint (bypasses cache, adds `Cache-Control: no-store`)
- CDN product is NOT used. All routing goes through ESA.

### Key Aliyun Services
- **OSS**: Object storage for static build artifacts. Path: `projects/{slug}/`
- **ESA**: Edge CDN with Edge Routines, Edge KV, Custom Hostnames
- **FC (Function Compute)**: Serverless hosting for Python apps via custom Docker images
- **ACR**: Container registry for Python app Docker images

### Edge Routine Deployment
Use `scripts/deploy-edge-routine.py` to deploy edge routine code:
```
docker exec miaobu-backend python /app/../scripts/deploy-edge-routine.py
```
Flow: `GetRoutineStagingCodeUploadInfo` → OSS upload → `CommitRoutineStagingCode` → `PublishRoutineCodeVersion`
API version: ESA 2024-09-10 (NOT DCDN 2018-01-15)

### Edge KV Schema
Key: hostname (e.g., `myproject.metavm.tech` or `custom.example.com`)
Value (JSON):
```json
{
  "type": "static" | "python",
  "oss_path": "projects/{slug}",       // static only
  "fc_endpoint": "https://...",         // python only
  "project_slug": "...",
  "deployment_id": 123,
  "commit_sha": "abc123",
  "updated_at": "2026-..."
}
```

## Key Files

### Backend
- `backend/app/api/v1/domains_esa.py` - Custom domain management (ESA Custom Hostnames, Edge KV, SSL)
- `backend/app/services/esa.py` - Aliyun ESA API client (Edge KV, Custom Hostnames, cache purge, SaaS managers)
- `backend/app/services/github.py` - GitHub API client (OAuth, repos, webhooks, build detection)
- `backend/app/services/build_detector.py` - Auto-detect framework, build/install commands, output dir from package.json
- `backend/app/services/oss.py` - Aliyun OSS upload/delete
- `backend/app/services/fc.py` - Aliyun Function Compute service
- `backend/app/models/__init__.py` - SQLAlchemy models (User, Project, Deployment, CustomDomain, etc.)
- `backend/app/config.py` - Settings (env vars, Aliyun credentials)

### Worker
- `worker/tasks/build.py` - Static site build pipeline (clone → install → build)
- `worker/tasks/build_python.py` - Python app build pipeline (clone → Docker build → push to ACR → deploy to FC)
- `worker/tasks/deploy.py` - OSS upload + Edge KV update + ESA cache purge
- `worker/celery_app.py` - Celery configuration

### Frontend
- `frontend/src/pages/ImportRepositoryPage.tsx` - Repository import with build config detection
- `frontend/src/pages/ProjectDetailPage.tsx` - Project dashboard with deployments
- `frontend/src/pages/ProjectSettingsPage.tsx` - Project settings (build config, domains, env vars)
- `frontend/src/components/EnvironmentVariables.tsx` - Env vars management UI

### Edge
- `edge-routine.js` - Single source of truth for ESA Edge Routine code

## Important Technical Details

### SSL for Subdomains
`*.metavm.tech` subdomains are covered by a wildcard certificate. When adding a metavm.tech subdomain as a custom domain:
- No ESA Custom Hostname (SaaS manager) is created
- `ssl_status` should be set to `ACTIVE` immediately (not `VERIFYING`)
- `esa_saas_id` will be `None`

### ESA API Gotchas
- Cache purge action is `PurgeCaches` (plural), NOT `PurgeCache`
- Content format for file purge: `json.dumps({'Files': [url1, url2]})`
- Content format for hostname purge: `json.dumps({'Hostnames': [host1]})`
- Edge Routine APIs are on ESA endpoint (2024-09-10), not DCDN (2018-01-15)
- Edge KV uses `new EdgeKV({ namespace: "miaobu" })` constructor (not `EDGE_KV` global)
- Edge Routine format is ES Module (`export default { async fetch(request, env) {...} }`)

### Build Detection
- `BuildDetector` in `build_detector.py` detects framework from `package.json` dependencies
- Build commands should always use `npm run build` / `pnpm run build` / `yarn run build` (never hardcoded binary names like `slidev build`)
- When a lockfile (pnpm-lock.yaml, yarn.lock) is detected, BOTH `install_command` and `build_command` must be overridden
- Python project detection looks for requirements.txt, pyproject.toml, Pipfile

### Deploy Flow (Static)
1. Clone repo → install deps → build → upload to OSS (`projects/{slug}/`)
2. Write Edge KV entry for `{slug}.metavm.tech`
3. Update custom domains with auto-update enabled
4. Purge ESA cache for hostname

### Deploy Flow (Python)
1. Clone repo → Docker build → push to ACR → deploy to FC
2. Write Edge KV entry for `{slug}.metavm.tech` with `type: "python"` and `fc_endpoint`
3. `deployment_url` is the subdomain URL (not raw FC endpoint)

## Common Operations

### Rebuild/redeploy a service
```bash
docker compose up -d --build backend
docker compose up -d --build worker
```

### Database access
```bash
docker exec miaobu-backend python -c "
import sys; sys.path.insert(0, '/app')
from app.database import SessionLocal
db = SessionLocal()
# ... queries ...
db.close()
"
```

### ESA cache purge
Done automatically during deploy via `esa_service.purge_host_cache([hostname])`.

## Base Domain
The base domain is `metavm.tech` (configured as `cdn_base_domain` in settings).
Subdomains: `{slug}.metavm.tech`
