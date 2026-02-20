# Miaobu - Static, Node.js & Python Deployment Platform

## Project Overview
Miaobu is a Vercel-like deployment platform that deploys GitHub repositories to Aliyun cloud infrastructure. It supports static sites (Node.js build), Node.js backend apps (Express/Fastify/NestJS/Koa/Hapi), and Python web apps (FastAPI/Flask/Django).

## Architecture

### Services (docker-compose)
- **backend** (port 8000): FastAPI API server
- **frontend** (port 3000): React + Vite + TypeScript UI
- **postgres** (port 5433): PostgreSQL 16 database
- **redis** (port 6379): Redis

### Traffic Routing (ESA-only architecture)
ALL traffic routes through Aliyun ESA (Edge Security Acceleration):
```
*.metavm.tech  →  ESA  →  Edge Routine  →  KV lookup  →  OSS (static) or FC (Node.js/Python)
custom domains →  ESA  →  Edge Routine  →  KV lookup  →  OSS (static) or FC (Node.js/Python)
```
- **Edge Routine** (`edge-routine.js`): ES Module format, uses `new EdgeKV({ namespace: "miaobu" })` for routing decisions
- **Static sites**: Edge Routine rewrites URL path (keeps same host for ESA caching), ESA fetches from OSS origin
- **Node.js/Python apps**: Edge Routine proxies directly to Function Compute endpoint (bypasses cache, adds `Cache-Control: no-store`)
- CDN product is NOT used. All routing goes through ESA.

### Key Aliyun Services
- **OSS**: Object storage for static build artifacts. Path: `projects/{slug}/{deployment_id}/`
- **ESA**: Edge CDN with Edge Routines, Edge KV, Custom Hostnames
- **FC (Function Compute)**: Serverless hosting for Node.js and Python apps via code package mode
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
  "type": "static" | "node" | "python",
  "oss_path": "projects/{slug}/{deployment_id}",  // static only
  "fc_endpoint": "https://...",         // node/python only
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
- `backend/app/services/build_detector.py` - Auto-detect framework, build/install commands, output dir from package.json; also detects Node.js backend frameworks (Express, Fastify, NestJS, Koa, Hapi)
- `backend/app/services/oss.py` - Aliyun OSS upload/delete
- `backend/app/services/fc.py` - Aliyun Function Compute service (Python + Node.js)
- `backend/app/models/__init__.py` - SQLAlchemy models (User, Project, Deployment, CustomDomain, etc.)
- `backend/app/config.py` - Settings (env vars, Aliyun credentials)

### Backend (Public API)
- `backend/app/api/v1/public/router.py` - Aggregates all public API sub-routers
- `backend/app/api/v1/public/projects.py` - Project CRUD (list, get, update, delete)
- `backend/app/api/v1/public/deployments.py` - Deployment management (list, get, logs, trigger, cancel, rollback)
- `backend/app/api/v1/public/domains.py` - Custom domain management (list, add, verify, delete)
- `backend/app/api/v1/public/env_vars.py` - Environment variable management (list, create, delete)
- `backend/app/api/v1/public/user.py` - User profile endpoint
- `backend/app/api/v1/public/helpers.py` - Pagination, response formatting utilities
- `backend/app/api/v1/api_tokens.py` - API token create/list/revoke (JWT-only)

### Frontend
- `frontend/src/pages/ImportRepositoryPage.tsx` - Repository import with build config detection
- `frontend/src/pages/ProjectDetailPage.tsx` - Project dashboard with deployments
- `frontend/src/pages/ProjectSettingsPage.tsx` - Project settings (build config, domains, env vars)
- `frontend/src/pages/AccountSettingsPage.tsx` - API token management UI
- `frontend/src/components/EnvironmentVariables.tsx` - Env vars management UI
- `frontend/src/components/DomainsManagement.tsx` - Custom domain management (DNS config, deployment promotion, auto-update toggle)
- `frontend/src/components/Toast.tsx` - Shared toast notification provider (`ToastProvider` + `useToast` hook)
- `frontend/src/components/Logo.tsx` - SVG logo component (cat paw mark)

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

### Frontend Toast Notifications
- **Never use browser `alert()`** — use the shared `useToast()` hook from `frontend/src/components/Toast.tsx`.
- `ToastProvider` wraps the app in `App.tsx`. Any component can call `const { toast } = useToast()` then `toast('message', 'success' | 'error' | 'warning' | 'info')`.
- Toast animations (`animate-toast-in`, `animate-toast-out`) are defined in `tailwind.config.js`.

### Frontend Logo
- Logo component: `frontend/src/components/Logo.tsx` — renders an inline SVG cat paw mark (秒部 ≈ 喵步 wordplay).
- Favicon: `frontend/public/logo.svg`.
- Used in: Layout sidebar, Layout mobile header, LandingPage navbar, LoginPage.

### ICP Domain Handling
- When ESA `CreateCustomHostname` succeeds but the domain lacks ICP filing, ESA marks the hostname `offline` (status=`pending` in our DB).
- The verify endpoint returns `verified: true` with `icp_required: true` and a Chinese-language message.
- Frontend checks `result.icp_required` and shows a warning toast instead of the generic success message.
- Domain list shows a `需要 ICP 备案` badge when `is_verified && esa_status === 'pending'`.
- DNS instructions modal shows an ICP-specific warning banner with link to `beian.aliyun.com` when `esa_status === 'pending'`.

### Backend Error Message Gotcha
- In `domains_esa.py`, when ESA provisioning fails, the error dict uses key `'error'` (not `'message'`). Use `provision_result.get('error')` to extract the message.

### Build Detection
- `BuildDetector` in `build_detector.py` detects framework from `package.json` dependencies
- Build commands should always use `npm run build` / `pnpm run build` / `yarn run build` (never hardcoded binary names like `slidev build`)
- When a lockfile (pnpm-lock.yaml, yarn.lock) is detected, BOTH `install_command` and `build_command` must be overridden
- Python project detection looks for requirements.txt, pyproject.toml, Pipfile
- Node.js backend detection: `detect_from_node_backend()` checks for Express, Fastify, NestJS, Koa, Hapi in production dependencies. Falls back to plain Node.js server detection: if `scripts.start` looks like a server command (`node xxx.js`, `ts-node`, `nodemon`, or contains "server") and no frontend framework in deps → detected as `node` type.
- For Node.js backend `start_command`: use the actual `scripts.start` value (e.g., `node index.js`), NOT `"npm start"`, because `npm` binary doesn't work reliably in the FC layer.

### Deploy Flow (Static)
1. Clone repo → install deps → build → upload to OSS (`projects/{slug}/{deployment_id}/`)
2. Write Edge KV entry for `{slug}.metavm.tech` with versioned `oss_path`
3. Update custom domains with auto-update enabled
4. Purge ESA cache for hostname
5. Trigger `cleanup_old_deployments` (keeps 3 most recent, protects custom-domain-pinned, marks old as `PURGED`)

### Deploy Flow (Python) — In-Place Update
1. Clone repo → install deps to `python_deps/` → zip → upload to OSS
2. GHA callback triggers inline deploy: `create_or_update_function("miaobu-{slug}", ...)` (~300ms, zero-downtime)
3. Update Edge KV with new deployment metadata (commit_sha, deployment_id)
4. Sync custom domains, purge cache
5. FC function name is stable: `miaobu-{slug}` (not per-deployment)
6. `deployment_url` is the subdomain URL (not raw FC endpoint)

### Deploy Flow (Node.js) — In-Place Update
1. Clone repo → install deps → optional build → prune devDeps → zip → upload to OSS
2. GHA callback triggers inline deploy: `create_or_update_node_function("miaobu-{slug}", ...)` (~300ms, zero-downtime)
3. FC function uses Node.js 20 layer (`NODEJS_LAYER_ARN`) with `custom.debian10` runtime
4. Bootstrap sets `PATH=/opt/nodejs/bin:$PATH`, `NODE_ENV=production`, `PORT=9000`
5. Update Edge KV entry for `{slug}.metavm.tech` with `type: "node"` and `fc_endpoint`
6. Edge routine treats `type: "node"` identically to `type: "python"` (both proxy to FC)

### FC (Function Compute) Gotchas
- **FC 3.0 URL format**: FC assigns unique subdomain hashes (e.g., `miaobu-ple-node-wobfgfxhse`) that **cannot be predicted** from the function name. You cannot construct URLs from `{function_name}.{account_id}.{region}.fcapp.run`. The URL must be extracted from the trigger response: `response.body.http_trigger.url_internet`.
- **npm binary broken in FC layer**: `/opt/nodejs/bin/npm` uses relative `require('../lib/cli.js')` that doesn't resolve in the layer directory structure. Route npm commands through `node /opt/nodejs/lib/node_modules/npm/bin/npm-cli.js` directly. Same for npx via `npx-cli.js`.
- **GHA build step validation**: The `build-node` workflow must check if the npm script actually exists in `package.json` before running (e.g., `npm run build` fails if there's no `build` script). The workflow has a guard for this.

### Python `or` Operator Gotcha
- `project.build_command or "npm run build"` treats empty string `""` as falsy, always returning the default. When a field can legitimately be empty (e.g., no build step for a Node.js project), use explicit `if project.build_command else ""` instead of `or`.

### Dashboard Stats
- `GET /api/v1/projects/stats/dashboard` returns `active_deployments` and `builds_this_month`.
- `active_deployments` = deployments currently in progress (queued/cloning/building/uploading/deploying), NOT the number of projects with a deployed status.
- `builds_this_month` = total deployments created since the 1st of the current month.
- Frontend: `DashboardPage.tsx` fetches via `api.getDashboardStats()`.

### Query Ordering
- Always add explicit `order_by()` to SQLAlchemy queries that return lists. PostgreSQL does not guarantee row order without it.
- Project list: `order_by(Project.created_at.desc())` — newest first.

### datetime.utcnow() is BANNED
- PostgreSQL session timezone is Asia/Shanghai (+08:00). `datetime.utcnow()` returns naive datetimes that PG misinterprets as local time → 8-hour offset on `deployed_at`, `verified_at`, etc.
- **ALWAYS** use `datetime.now(timezone.utc)` (from `datetime import timezone`). This produces timezone-aware datetimes that PG handles correctly.
- `server_default=func.now()` (used for `created_at`/`updated_at`) is fine — PG's `NOW()` is always correct.

### Self-Hosting Bootstrap Trap
- Miaobu deploys itself (project `miaobu1`, ID 18). The CURRENTLY RUNNING FC code processes each deployment.
- When pushing a fix that changes the deploy flow itself, the first deploy runs on the OLD (buggy) code. May need a second push or webhook re-delivery.
- If a deploy fails during self-hosting, check webhook deliveries: `gh api repos/wizardleeen/miaobu/hooks/596729288/deliveries`

## Deployment & Operations

### Code Deployment
Code is deployed via `git push` to the `main` branch. Docker containers are **no longer used** for deployment. A push to main triggers the hosting platform to redeploy backend and frontend automatically.

### GitHub Actions Build Pipeline
- Builds are triggered via `repository_dispatch` (type `miaobu-build`) when a user deploys their project.
- Workflow: `.github/workflows/build.yml` — has `build-static`, `build-python`, and `build-node` jobs.
- All API calls (clone-token, env-vars, callbacks) have **retry logic** (5 attempts, 10s apart) to survive backend redeploys. Only retries on 5xx/connection errors; fails immediately on 4xx.
- Callback helper: `.github/scripts/callback.sh` — sends signed POST to the build-callback endpoint with retry.
- **Key issue**: when a git push redeploys the backend, any concurrent GHA builds will hit the API during the restart window. The retry logic handles this.

### ESA cache purge
Done automatically during deploy via `esa_service.purge_host_cache([hostname])`.

## Public API & Token Auth
- **Public API router**: `backend/app/api/v1/public/` — projects, deployments, domains, env vars, user endpoints
  - Mounted at `/api/v1/public` in `backend/app/main.py`
  - Uses `get_current_user_flexible` (dual auth: API token or JWT)
  - Response helpers in `public/helpers.py`: `paginated_response()`, `single_response()`, `error_response()`
- **API Token management**: `backend/app/api/v1/api_tokens.py` — create/list/revoke tokens (JWT-only, at `/api/v1/tokens`)
- **ApiToken model**: `backend/app/models/__init__.py` — SHA-256 hashed storage, `mb_live_` prefix, optional expiration
- **Dual auth middleware**: `backend/app/core/security.py` — `get_current_user_flexible` checks Bearer token as API token first (prefix + hash lookup), falls back to JWT
- **Frontend token management**: `frontend/src/pages/AccountSettingsPage.tsx` — accessible from Settings page
- **Environment variable encryption**: Values in `environment_variables` table are encrypted at rest (Fernet). Direct SQL inserts bypass encryption — always use the API.

## API Docs Site (Astro Starlight)
- **Location**: `docs/` directory — Astro 5 + Starlight 0.37
- **Package manager**: pnpm (not npm). `pnpm.onlyBuiltDependencies` in `package.json` whitelists `esbuild` and `sharp`.
- **Content config**: `docs/src/content.config.ts` is required (Astro 5 no longer auto-generates content collections). Uses `docsLoader()` + `docsSchema()` from Starlight.
- **Locale config**: Monolingual Chinese site uses `defaultLocale: 'root'` with `locales: { root: { label: '简体中文', lang: 'zh-CN' } }`.
- **Starlight 0.33+ breaking change**: `social` config changed from object to array: `[{ icon: 'github', label: 'GitHub', href: '...' }]`.
- **API base URL in docs**: `https://miaobu-api.metavm.tech/api/v1/public` — hardcoded across markdown files.
- **Build**: `pnpm run build` from `docs/` directory. Output in `docs/dist/`.
- **Gitignore**: `docs/node_modules/`, `docs/dist/`, `docs/.astro/` are excluded.
- **Frontend link**: Layout sidebar has "API 文档" link (external, new tab) when `VITE_DOCS_URL` env var is set. Production value: `https://miaobu-docs.metavm.tech`.

## Base Domain
The base domain is `metavm.tech` (configured as `cdn_base_domain` in settings).
Subdomains: `{slug}.metavm.tech`

