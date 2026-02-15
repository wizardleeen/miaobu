# Testing Phase 6: Webhook Automation

This guide provides step-by-step instructions for testing the webhook automation feature.

## Prerequisites

- Docker and Docker Compose installed
- GitHub account with a test repository
- GitHub OAuth app configured
- Alibaba Cloud credentials configured

## Setup

### 1. Start Services

```bash
cd /home/leen/miaobu
docker-compose up -d
```

Verify all services are running:
```bash
docker-compose ps

# Should show:
# - postgres (healthy)
# - redis (healthy)
# - backend (running)
# - worker (running)
# - frontend (running)
```

### 2. Create Test Repository

**Option A: Use existing repository**
- Must have a Node.js project with `package.json`
- Must have a build script (e.g., `npm run build`)

**Option B: Create new test repository**

```bash
# Create new repo on GitHub
# Clone it locally
git clone https://github.com/YOUR_USERNAME/test-webhook-deploy.git
cd test-webhook-deploy

# Initialize Vite project
npm create vite@latest . -- --template react
npm install

# Commit and push
git add .
git commit -m "Initial commit"
git push origin main
```

### 3. Expose Local Backend (for local testing)

If testing locally, you need to expose your backend to GitHub:

```bash
# Install ngrok (if not already installed)
# On Ubuntu/Debian:
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Start ngrok
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

Update `.env`:
```bash
BACKEND_URL=https://abc123.ngrok.io
```

Restart backend:
```bash
docker-compose restart backend worker
```

## Test 1: Import Repository with Automatic Webhook

### Steps:

1. **Login to Miaobu:**
   - Navigate to http://localhost:5173
   - Click "Sign in with GitHub"
   - Authorize the application

2. **Import Repository:**
   - Click "Import Repository"
   - Find your test repository
   - Click "Analyze"
   - Verify build settings are detected
   - Click "Import Project"

3. **Verify Webhook Creation:**

   **In Miaobu UI:**
   - Go to project detail page
   - Look for "Auto Deploy" section
   - Should show green "✓ Enabled" badge
   - Should show "Deploys on push to main"

   **In GitHub:**
   - Go to repository settings
   - Click "Webhooks"
   - Should see webhook with:
     - Payload URL: `{BACKEND_URL}/api/v1/webhooks/github/{project_id}`
     - Content type: `application/json`
     - Secret: `********` (hidden)
     - Events: Just the push event
     - Active: ✓

4. **Check Recent Deliveries:**
   - Click on the webhook
   - Should see "ping" event (GitHub's initial test)
   - Status: 200 OK
   - Response: `{"status":"ok","message":"Webhook received and verified"}`

### Expected Results:

✅ Project imported successfully
✅ Webhook created in GitHub
✅ Webhook shows "✓ Enabled" in UI
✅ Ping event delivered successfully
✅ No errors in backend logs

### Troubleshooting:

❌ **Webhook not created:**
- Check backend logs: `docker-compose logs backend`
- Verify GitHub token has repo permissions
- Check `BACKEND_URL` is set correctly

❌ **Webhook shows error:**
- Check GitHub webhook delivery details
- Verify ngrok is running (for local testing)
- Check backend is accessible from internet

## Test 2: Automatic Deployment on Push

### Steps:

1. **Make a change to your test repository:**

```bash
cd test-webhook-deploy

# Make a visible change
echo "<p>Webhook Test $(date)</p>" >> public/index.html

# Or modify src/App.jsx
sed -i 's/Vite + React/Vite + React + Webhooks!/g' src/App.jsx
```

2. **Commit and push:**

```bash
git add .
git commit -m "Test webhook deployment"
git push origin main
```

3. **Verify in Miaobu:**

   **Watch for new deployment:**
   - Navigate to project detail page
   - Should see new deployment appear within 5 seconds
   - Status should progress: `queued` → `cloning` → `building` → `uploading` → `deployed`

   **Check deployment details:**
   - Commit SHA should match your push
   - Commit message should be "Test webhook deployment"
   - Author should be your name

4. **Verify in GitHub:**

   **Check webhook delivery:**
   - Go to repository → Settings → Webhooks
   - Click on your webhook
   - Click "Recent Deliveries"
   - Find the "push" event
   - Status should be 200 OK
   - Response should show deployment created

5. **Verify deployment:**
   - Wait for build to complete
   - Click "Preview" button on deployment
   - Should see your changes live

### Expected Results:

✅ Push triggers webhook immediately
✅ Deployment created automatically
✅ Build completes successfully
✅ Site shows updated content
✅ Webhook delivery shows 200 OK

### Troubleshooting:

❌ **No deployment created:**
- Check webhook delivery in GitHub
- Look for error response in delivery details
- Check backend logs: `docker-compose logs backend`
- Verify webhook signature is valid

❌ **Deployment fails:**
- Check build logs in deployment
- Verify build commands are correct
- Check worker logs: `docker-compose logs worker`

## Test 3: Branch Filtering

### Steps:

1. **Create feature branch:**

```bash
cd test-webhook-deploy

# Create and switch to feature branch
git checkout -b feature/test-branch

# Make a change
echo "<p>Feature branch test</p>" >> public/index.html

# Commit and push
git add .
git commit -m "Test feature branch (should not deploy)"
git push origin feature/test-branch
```

2. **Verify in Miaobu:**
   - Go to project detail page
   - Should NOT see new deployment
   - Deployment count should remain unchanged

3. **Check webhook delivery:**
   - Go to GitHub → Settings → Webhooks → Recent Deliveries
   - Find the push to `feature/test-branch`
   - Status: 200 OK
   - Response: `{"status":"ignored","message":"Push to 'feature/test-branch' ignored (only 'main' triggers deployment)"}`

4. **Push to main branch:**

```bash
# Switch back to main
git checkout main

# Merge feature branch
git merge feature/test-branch

# Push
git push origin main
```

5. **Verify deployment is created:**
   - Should see new deployment in Miaobu
   - Deployment should process normally

### Expected Results:

✅ Push to feature branch ignored
✅ No deployment created for feature branch
✅ Webhook response explains why ignored
✅ Push to main branch triggers deployment

### Troubleshooting:

❌ **Feature branch triggered deployment:**
- Check project default_branch setting
- Verify webhook response in GitHub
- Check branch filtering logic in logs

## Test 4: Duplicate Prevention

### Steps:

1. **Trigger same commit twice:**

```bash
# Get current commit SHA
COMMIT_SHA=$(git rev-parse HEAD)
echo "Current commit: $COMMIT_SHA"
```

2. **Manually trigger webhook (simulate GitHub):**

```bash
# Get webhook URL and project ID from GitHub
WEBHOOK_URL="http://localhost:8000/api/v1/webhooks/github/5"
SECRET="your-webhook-secret-from-database"

# Create test payload
PAYLOAD='{
  "ref": "refs/heads/main",
  "after": "'$COMMIT_SHA'",
  "head_commit": {
    "id": "'$COMMIT_SHA'",
    "message": "Duplicate test",
    "author": {"name": "Test User"}
  }
}'

# Calculate signature
SIGNATURE="sha256=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)"

# Send webhook
curl -X POST "$WEBHOOK_URL" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

3. **Verify response:**

First call:
```json
{
  "status": "success",
  "message": "Deployment triggered for commit abc123d",
  "deployment_id": 42
}
```

Second call:
```json
{
  "status": "skipped",
  "message": "Deployment for commit abc123d already exists",
  "deployment_id": 42
}
```

### Expected Results:

✅ First webhook creates deployment
✅ Second webhook skips deployment
✅ Only one deployment exists per commit
✅ Both webhooks return 200 OK

## Test 5: Signature Verification

### Steps:

1. **Test with invalid signature:**

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/github/5" \
  -H "X-Hub-Signature-256: sha256=invalid" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d '{"ref":"refs/heads/main","head_commit":{"id":"abc123"}}'
```

**Expected response:**
```json
{
  "detail": "Invalid webhook signature"
}
```

Status code: 401 Unauthorized

2. **Test with missing signature:**

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/github/5" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d '{"ref":"refs/heads/main","head_commit":{"id":"abc123"}}'
```

**Expected response:**
Status code: 401 Unauthorized

### Expected Results:

✅ Invalid signature rejected
✅ Missing signature rejected
✅ Returns 401 Unauthorized
✅ No deployment created

## Test 6: Performance Testing

### Test webhook response time:

```bash
# Measure webhook response time
time curl -X POST "$WEBHOOK_URL" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -o /dev/null -s -w "%{time_total}\n"
```

**Expected:**
- Response time: < 200ms
- GitHub requires < 10 seconds

### Expected Results:

✅ Response time under 200ms
✅ Webhook handler doesn't block
✅ Build runs asynchronously

## Test 7: End-to-End Workflow

### Complete deployment workflow:

1. **Make multiple changes:**

```bash
# Change 1
echo "Update 1" >> README.md
git add .
git commit -m "Update 1"
git push origin main

# Wait 30 seconds

# Change 2
echo "Update 2" >> README.md
git add .
git commit -m "Update 2"
git push origin main

# Wait 30 seconds

# Change 3
echo "Update 3" >> README.md
git add .
git commit -m "Update 3"
git push origin main
```

2. **Verify all deployments:**
   - Should see 3 separate deployments
   - Each should build sequentially
   - All should complete successfully
   - Each should have different commit SHAs

3. **Verify final state:**
   - Latest deployment should be "Update 3"
   - Preview should show all changes
   - Old deployments should still be accessible

### Expected Results:

✅ All 3 deployments created
✅ Each deployment builds independently
✅ No conflicts or race conditions
✅ All deployments successful

## Common Issues and Solutions

### Issue 1: Webhook not receiving events

**Symptoms:**
- Push to GitHub doesn't trigger webhook
- No entries in "Recent Deliveries"

**Debug:**
```bash
# Check if webhook exists
curl https://api.github.com/repos/OWNER/REPO/hooks \
  -H "Authorization: token YOUR_GITHUB_TOKEN"

# Should show webhook with your URL
```

**Solutions:**
- Verify webhook is active in GitHub
- Check webhook URL is correct
- For local testing, ensure ngrok is running
- Check firewall allows incoming connections

### Issue 2: 401 Unauthorized errors

**Symptoms:**
- Webhook delivery shows 401 error
- Response: "Invalid webhook signature"

**Debug:**
```bash
# Check project webhook secret
docker-compose exec backend python -c "
from app.database import SessionLocal
from app.models import Project
db = SessionLocal()
project = db.query(Project).filter(Project.id == 5).first()
print(f'Secret: {project.webhook_secret}')
"
```

**Solutions:**
- Verify webhook secret matches in GitHub
- Check secret doesn't have special characters
- Recreate webhook if secret is corrupted

### Issue 3: Deployments not building

**Symptoms:**
- Webhook creates deployment
- Deployment stuck in "queued" status

**Debug:**
```bash
# Check Celery worker
docker-compose logs worker

# Check Redis
docker-compose exec redis redis-cli ping
# Should return: PONG

# Check queue length
docker-compose exec redis redis-cli llen builds
```

**Solutions:**
- Restart worker: `docker-compose restart worker`
- Check worker has access to Docker socket
- Verify Redis connection

### Issue 4: Slow webhook responses

**Symptoms:**
- Webhook takes > 1 second to respond
- GitHub shows slow delivery times

**Debug:**
```bash
# Check backend performance
docker-compose logs backend | grep "webhook"

# Check database performance
docker-compose exec postgres psql -U miaobu -c "
SELECT * FROM deployments ORDER BY created_at DESC LIMIT 10;
"
```

**Solutions:**
- Add database indexes
- Optimize webhook handler
- Use connection pooling
- Cache project lookups

## Success Checklist

Before considering Phase 6 complete, verify:

- [ ] Repository import automatically creates webhook
- [ ] Webhook appears in GitHub settings
- [ ] Push to main branch triggers deployment
- [ ] Push to feature branch is ignored
- [ ] Duplicate commits are prevented
- [ ] Invalid signatures are rejected
- [ ] Webhook response time < 200ms
- [ ] Frontend shows webhook status
- [ ] Build logs show commit info
- [ ] Deployed site shows latest changes

## Next Steps

After successful testing:

1. **Production deployment:**
   - Deploy to production server
   - Update `BACKEND_URL` in production `.env`
   - Verify webhooks work in production

2. **Monitor webhooks:**
   - Set up logging for webhook events
   - Monitor webhook failure rate
   - Track deployment success rate

3. **Documentation:**
   - Document webhook setup for users
   - Create troubleshooting guide
   - Add webhook management to admin panel

---

**Phase 6 Testing Complete!** 🎉

If all tests pass, you're ready to proceed to Phase 7: Custom Domains.
