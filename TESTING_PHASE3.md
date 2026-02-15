# Phase 3 Testing Guide

## Quick Start

```bash
# 1. Rebuild services with new worker code
docker-compose build worker backend

# 2. Start all services
docker-compose up -d

# 3. Check services are running
docker-compose ps

# 4. Watch logs (optional)
docker-compose logs -f worker
```

## Test Checklist

### ✅ Test 1: First Deployment

1. **Navigate to project**
   ```
   http://localhost:5173/projects/{id}
   ```

2. **Click "🚀 Deploy" button**
   - Should show "Deploying..." immediately
   - Button becomes disabled

3. **Watch status change**
   - queued → cloning → building → uploading → deployed
   - Page auto-refreshes every 5 seconds

4. **View logs**
   - Click "View Logs" on deployment card
   - Should see real-time log output
   - Logs update every 2 seconds during build

### ✅ Test 2: Log Streaming

**Expected Log Sections:**

```
============================================================
STEP 1: CLONING REPOSITORY
============================================================
Cloning repository: https://github.com/...
✓ Repository cloned successfully

============================================================
STEP 2: INSTALLING DEPENDENCIES
============================================================
Command: npm install
No cache available, installing from scratch...
✓ Dependencies installed successfully
✓ Dependencies cached for future builds

============================================================
STEP 3: RUNNING BUILD
============================================================
Command: npm run build
✓ Build completed successfully

============================================================
STEP 4: BUILD VERIFICATION
============================================================
✓ Output directory found
✓ Build produced X files

============================================================
BUILD COMPLETED SUCCESSFULLY
============================================================
```

### ✅ Test 3: Build Caching

1. **Trigger second deployment**
   - Click "🚀 Deploy" again
   - Should start new build

2. **Check for cache hit**
   - View logs
   - Look for: "Cache hit! Restoring node_modules from cache"
   - Install step should be much faster (~2-5s vs 30-120s)

3. **Verify speedup**
   - First build: 1-3 minutes
   - Second build: 30-90 seconds

### ✅ Test 4: Cancel Deployment

1. **Start a deployment**
   - Click "🚀 Deploy"

2. **Immediately cancel**
   - Click "Cancel" button
   - Confirm cancellation

3. **Verify cancellation**
   - Status changes to `cancelled`
   - Logs show termination
   - New deployment can be triggered

### ✅ Test 5: Build Failure

**Test with project that has build errors:**

1. **Create test project with failing build**
   - Modify package.json to have invalid script
   - Or create syntax error in source

2. **Trigger deployment**

3. **Verify failure handling**
   - Status changes to `failed`
   - Error message displayed
   - Logs show build error
   - Can trigger new deployment

### ✅ Test 6: Multiple Deployments

1. **Trigger 3-4 deployments**
   - Wait for each to complete
   - Or trigger rapid succession

2. **Check deployment list**
   - All deployments shown
   - Newest at top
   - Each has correct status
   - Each has unique commit info

3. **Expand logs for each**
   - Each deployment has own logs
   - Logs don't interfere

## Troubleshooting

### Worker not starting

```bash
# Check worker logs
docker-compose logs worker

# Common issues:
# 1. Redis not available
docker-compose ps redis

# 2. Database connection issue
docker-compose ps postgres

# 3. Docker socket not mounted
docker-compose exec worker docker ps
```

### Builds not starting

```bash
# Check Celery can connect to Redis
docker-compose exec worker python -c "
from celery_app import app
print(app.control.inspect().active())
"

# Check queue
docker-compose exec worker python -c "
import redis
r = redis.from_url('redis://redis:6379/0')
print(r.llen('celery'))
"
```

### Docker permission issues

```bash
# Worker needs access to Docker socket
docker-compose exec worker docker ps

# If permission denied:
# 1. Add user to docker group (host)
# 2. Or run with privileged mode (not recommended)
```

### Logs not updating

```bash
# Check Redis is working
docker-compose exec redis redis-cli ping

# Check log key exists
docker-compose exec redis redis-cli KEYS "build:logs:*"

# Check log content
docker-compose exec redis redis-cli LRANGE "build:logs:1" 0 -1
```

### Build hangs

```bash
# Check running containers
docker ps | grep miaobu-build

# Check worker status
docker-compose logs --tail=50 worker

# Force restart worker
docker-compose restart worker
```

## Manual Testing Commands

### Trigger deployment via API

```bash
curl -X POST http://localhost:8000/api/v1/projects/1/deploy \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### Get deployment status

```bash
curl http://localhost:8000/api/v1/deployments/1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get deployment logs

```bash
curl http://localhost:8000/api/v1/deployments/1/logs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Cancel deployment

```bash
curl -X POST http://localhost:8000/api/v1/deployments/1/cancel \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Performance Benchmarks

### Expected Timings

**Small Project (Vite + React):**
- First build: 60-90 seconds
- Cached build: 25-35 seconds

**Medium Project (Next.js):**
- First build: 120-180 seconds
- Cached build: 40-60 seconds

**Large Project (Monorepo):**
- First build: 180-300 seconds
- Cached build: 60-120 seconds

### Monitoring

```bash
# Watch resource usage
docker stats

# Watch build logs live
docker-compose logs -f --tail=100 worker

# Monitor Redis queue length
watch -n 1 'docker-compose exec redis redis-cli llen celery'
```

## Common Test Projects

### 1. Simple Vite Project
```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0"
  }
}
```
Expected: Fast build (~20-30s after deps)

### 2. Create React App
```json
{
  "scripts": {
    "build": "react-scripts build"
  },
  "dependencies": {
    "react": "^18.0.0",
    "react-scripts": "5.0.1"
  }
}
```
Expected: Medium build (~40-60s after deps)

### 3. Next.js Static
```json
{
  "scripts": {
    "build": "next build && next export"
  },
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.0.0"
  }
}
```
Expected: Longer build (~60-90s after deps)

## Success Indicators

✅ **Phase 3 is working if:**
1. Deployments can be triggered manually
2. Build status updates in real-time
3. Logs stream and are readable
4. Builds complete successfully for valid projects
5. Build errors are captured and displayed
6. Caching speeds up second builds
7. Cancellation works immediately
8. No orphaned Docker containers
9. Worker recovers from errors
10. Multiple deployments can queue

---

**Happy Testing!** 🚀

Need help? Check:
- Worker logs: `docker-compose logs worker`
- API docs: http://localhost:8000/docs
- Phase 3 summary: `PHASE3_SUMMARY.md`
