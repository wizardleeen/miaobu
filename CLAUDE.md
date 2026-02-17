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
- **OSS**: Object storage for static build artifacts. Path: `projects/{slug}/{deployment_id}/`
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
  "oss_path": "projects/{slug}/{deployment_id}",  // static only
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
- `worker/tasks/deploy.py` - OSS upload + Edge KV update + ESA cache purge + cleanup old deployments
- `worker/celery_app.py` - Celery configuration

### Frontend
- `frontend/src/pages/ImportRepositoryPage.tsx` - Repository import with build config detection
- `frontend/src/pages/ProjectDetailPage.tsx` - Project dashboard with deployments
- `frontend/src/pages/ProjectSettingsPage.tsx` - Project settings (build config, domains, env vars)
- `frontend/src/components/EnvironmentVariables.tsx` - Env vars management UI
- `frontend/src/components/DomainsManagement.tsx` - Custom domain management (DNS config, deployment promotion, auto-update toggle)

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
- `GetKv` API action returns 403 UnsupportedHTTPMethod — **do not use** `esa_service.get_edge_kv()`. Use `put_edge_kv()` directly with constructed values.

### FastAPI Endpoint Gotchas
- When a POST endpoint receives JSON body data, parameters MUST be wrapped in a Pydantic `BaseModel` class. Bare function parameters (e.g., `deployment_id: int`) are treated as **query parameters** by FastAPI, NOT parsed from JSON body. This causes silent failures where the value is always `None`.
- The `DeploymentStatus` enum exists in TWO places: `backend/app/models/__init__.py` (SQLAlchemy) AND `backend/app/schemas/__init__.py` (Pydantic response validation). Both must be kept in sync — adding a status to one but not the other causes 500 ResponseValidationError.
- When adding a new enum value to PostgreSQL: `ALTER TYPE deploymentstatus ADD VALUE IF NOT EXISTS 'PURGED'` — note enum labels are UPPERCASE in this project's DB.

### Deployment Lifecycle
- Statuses: `queued` → `cloning` → `building` → `uploading` → `deploying` → `deployed` → (optionally) `purged`
- `PURGED`: deployment record preserved for history, but OSS files deleted. Cannot be promoted. Excluded from domain deployment lists.
- Cleanup keeps 3 most recent `DEPLOYED` + any pinned to custom domains via `active_deployment_id`

### Frontend State Gotchas
- Modals that use `selectedDomain` (local state set via `setSelectedDomain`): this is a **stale snapshot**. After mutations, the local state must be updated manually (e.g., `setSelectedDomain(prev => ({...prev, field: newValue}))`), or the UI won't reflect changes until the modal is closed and reopened.
- Deploy button: `isDeploying` must stay `true` until `await refetch()` completes, otherwise there's a gap where neither `isDeploying` nor `hasActiveDeployment` is true and the button becomes clickable.
- Long modal content with `flex items-center justify-center`: when content exceeds viewport height, `items-center` pushes the top out of scrollable area. Use `items-start` instead.

### Build Detection
- `BuildDetector` in `build_detector.py` detects framework from `package.json` dependencies
- Build commands should always use `npm run build` / `pnpm run build` / `yarn run build` (never hardcoded binary names like `slidev build`)
- When a lockfile (pnpm-lock.yaml, yarn.lock) is detected, BOTH `install_command` and `build_command` must be overridden
- Python project detection looks for requirements.txt, pyproject.toml, Pipfile

### Deploy Flow (Static)
1. Clone repo → install deps → build → upload to OSS (`projects/{slug}/{deployment_id}/`)
2. Write Edge KV entry for `{slug}.metavm.tech` with versioned `oss_path`
3. Update custom domains with auto-update enabled
4. Purge ESA cache for hostname
5. Trigger `cleanup_old_deployments` (keeps 3 most recent, protects custom-domain-pinned, marks old as `PURGED`)

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

### Container volume mounts
- **backend**: only `backend/` is mounted at `/app`. Scripts outside `backend/` are NOT accessible inside the container.
- **worker**: `worker/` is mounted at `/app`. Has Docker socket access.

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
