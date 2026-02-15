# Webhook Setup Guide - Automatic Deployments

Enable automatic deployments whenever you push code to GitHub!

## What are Webhooks?

Webhooks allow GitHub to notify Miaobu when you push code. This triggers an automatic deployment without any manual intervention.

**Benefits:**
- 🚀 **Zero-touch deployments** - Just push code, and it deploys automatically
- ⚡ **Instant feedback** - See your changes live within minutes
- 🔄 **Continuous deployment** - Every push to main branch deploys
- 🎯 **Branch filtering** - Only main branch triggers deployments

## Automatic Setup (Recommended)

**Webhooks are created automatically when you import a repository!**

### Steps:

1. **Import Repository:**
   - Go to Projects → Import Repository
   - Select your repository
   - Click "Import Project"

2. **Webhook Created:**
   - Webhook is automatically configured in GitHub
   - You'll see "✓ Enabled" badge in project settings

3. **That's it!**
   - Push to your main branch
   - Watch deployment happen automatically

### Verify Webhook:

**In Miaobu:**
- Go to your project page
- Look for "Auto Deploy" section
- Should show green "✓ Enabled" badge

**In GitHub:**
- Go to repository Settings → Webhooks
- Should see webhook with Miaobu URL
- Recent Deliveries should show successful pings

## Manual Setup

If webhook wasn't created automatically or you deleted it:

### 1. Get Webhook Information

**Via Miaobu API:**

```bash
# Get your project ID from the URL
# Example: /projects/5 → project_id is 5

# Request webhook setup
curl -X POST "https://api.miaobu.app/api/v1/webhooks/projects/5/setup" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "status": "success",
  "webhook_id": 123456789,
  "webhook_url": "https://api.miaobu.app/api/v1/webhooks/github/5"
}
```

### 2. Configure in GitHub

1. **Go to Repository Settings:**
   - Navigate to your repository on GitHub
   - Click Settings → Webhooks
   - Click "Add webhook"

2. **Configure Webhook:**
   - **Payload URL:** Copy from Miaobu response
   - **Content type:** `application/json`
   - **Secret:** (Optional) Leave empty or contact support for secret
   - **Events:** Select "Just the push event"
   - **Active:** ✓ Checked

3. **Save Webhook:**
   - Click "Add webhook"
   - GitHub will send a test ping

4. **Verify:**
   - Check "Recent Deliveries" tab
   - Should see green checkmark ✓
   - Response: `{"status":"ok","message":"Webhook received and verified"}`

## How It Works

### Deployment Flow

```
1. You push code to GitHub
   ↓
2. GitHub sends webhook to Miaobu
   ↓
3. Miaobu verifies the webhook
   ↓
4. Miaobu creates deployment
   ↓
5. Build pipeline runs automatically
   ↓
6. Site deployed to CDN
   ↓
7. You get notified (coming soon!)
```

### What Gets Deployed?

**Only pushes to your default branch trigger deployments.**

Default branch is typically:
- `main` (most common)
- `master` (older repos)
- Custom branch (if configured)

**Feature branches are ignored:**
- Push to `feature/new-design` → No deployment
- Push to `develop` → No deployment
- Push to `main` → Deployment triggered ✓

## Testing Your Webhook

### Quick Test:

1. **Make a change:**
   ```bash
   echo "<!-- Webhook test -->" >> public/index.html
   git add .
   git commit -m "Test webhook"
   git push origin main
   ```

2. **Watch in Miaobu:**
   - Go to your project page
   - New deployment should appear within 5 seconds
   - Status will progress: queued → building → deployed

3. **Verify deployment:**
   - Click "Preview" when build completes
   - Your changes should be live

### Check Webhook Health:

**In GitHub:**
1. Go to Settings → Webhooks
2. Click on your webhook
3. Check "Recent Deliveries"
4. Look for green checkmarks ✓

**Healthy webhook shows:**
- Status: 200 OK
- Recent deliveries successful
- No error messages

## Troubleshooting

### Webhook Not Triggering

**Symptoms:**
- Push code but no deployment appears
- Webhook shows red X in GitHub

**Solutions:**

1. **Check webhook is active:**
   - GitHub → Settings → Webhooks
   - Ensure webhook is not disabled

2. **Verify webhook URL:**
   - Should be: `https://api.miaobu.app/api/v1/webhooks/github/{project_id}`
   - Check for typos or wrong project ID

3. **Check Recent Deliveries:**
   - Look for error messages
   - Common errors:
     - 401: Invalid signature
     - 404: Project not found
     - 500: Server error

4. **Recreate webhook:**
   ```bash
   # Delete webhook in GitHub
   # Then use Miaobu API to recreate
   curl -X POST "https://api.miaobu.app/api/v1/webhooks/projects/5/setup" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

### Wrong Branch Deploying

**Symptoms:**
- Feature branch pushes trigger deployments
- Want to change default branch

**Solutions:**

1. **Check project settings:**
   - Miaobu uses the repository's default branch
   - Change in GitHub: Settings → Branches → Default branch

2. **Update project:**
   - Reimport project to sync new default branch
   - Or contact support to update manually

### Duplicate Deployments

**Symptoms:**
- Multiple deployments for same commit
- Deployments appear twice

**Solutions:**

1. **Check for multiple webhooks:**
   - GitHub → Settings → Webhooks
   - Delete duplicate webhooks

2. **This is normal for:**
   - Force push
   - Rebase and push
   - Multiple GitHub integrations

### Deployment Fails

**Symptoms:**
- Webhook triggers but build fails
- Status shows "failed"

**Solutions:**

1. **Check build logs:**
   - Click on failed deployment
   - Expand logs to see error
   - Fix build issue in code

2. **Common issues:**
   - Build command incorrect
   - Missing dependencies
   - Output directory wrong
   - Node version mismatch

3. **Update build settings:**
   - Go to Project Settings
   - Update build configuration
   - Retry deployment

## Security

### How Webhooks are Secured

1. **Secret Token:**
   - Each webhook has a unique secret
   - GitHub signs every request with this secret
   - Miaobu verifies signature before processing

2. **HTTPS Only:**
   - All webhooks use HTTPS
   - Encrypted in transit
   - SSL certificate required

3. **Request Validation:**
   - Verifies GitHub signature
   - Checks project exists
   - Filters event types
   - Prevents replay attacks

### Best Practices

1. **Don't share webhook URLs:**
   - Each URL is project-specific
   - Contains project ID
   - Should be kept private

2. **Monitor webhook activity:**
   - Check Recent Deliveries regularly
   - Look for suspicious patterns
   - Report unusual activity

3. **Rotate secrets periodically:**
   - Contact support to rotate webhook secret
   - Reduces risk if compromised

## Advanced Configuration

### Custom Branch Deployment

Want to deploy from a branch other than main?

**Option 1: Change GitHub default branch:**
1. GitHub → Settings → Branches
2. Change default branch
3. Reimport project in Miaobu

**Option 2: Use manual deployments:**
- Webhook only triggers for default branch
- Use manual deploy button for other branches

### Multiple Repositories

Have multiple repositories?

**Each repository needs its own:**
- Miaobu project
- GitHub webhook
- Separate deployments

**To set up:**
1. Import each repository separately
2. Each gets its own webhook automatically
3. Push to any repo triggers only that project

### Webhook Events

Miaobu currently supports:
- ✅ Push events (for deployments)
- ✅ Ping events (for testing)

Future support planned for:
- ⏳ Pull request events (PR previews)
- ⏳ Release events (tagged deployments)
- ⏳ Deployment status events (notifications)

## FAQ

### Q: Does every push deploy?

**A:** Only pushes to the default branch (usually `main`) trigger deployments. Feature branches are ignored.

### Q: Can I disable auto-deploy?

**A:** Yes, delete the webhook in GitHub Settings → Webhooks. You can still manually deploy from Miaobu.

### Q: How fast are deployments?

**A:** Typical timeline:
- Webhook received: < 1 second
- Build starts: < 5 seconds
- Build completes: 1-5 minutes (depends on project size)
- CDN purge: 1-2 minutes
- **Total: ~2-7 minutes from push to live**

### Q: What happens if build fails?

**A:**
- Webhook still triggers
- Deployment is created
- Build runs but fails
- Previous deployment remains live
- You can fix and push again

### Q: Can I see webhook history?

**A:**
- GitHub: Settings → Webhooks → Recent Deliveries
- Miaobu: Check deployment history (each shows if triggered by webhook)

### Q: Cost of webhooks?

**A:**
- GitHub webhooks: Free
- Miaobu processing: Included in your plan
- Build time: Counts toward your build minutes

### Q: Webhook stopped working?

**A:**
- Check webhook is active in GitHub
- Verify Recent Deliveries for errors
- Recreate webhook if needed
- Contact support if persistent issues

## Getting Help

### Need assistance?

1. **Check webhook deliveries:**
   - GitHub → Settings → Webhooks → Recent Deliveries
   - Look for error messages

2. **Check build logs:**
   - Miaobu → Project → Failed deployment
   - Read error messages

3. **Contact support:**
   - Include: Project ID, Repository name, Error message
   - We'll help debug the issue

### Useful Resources

- **GitHub Webhooks Documentation:** https://docs.github.com/webhooks
- **Miaobu API Documentation:** https://api.miaobu.app/docs
- **Miaobu Community:** https://community.miaobu.app

---

**Webhooks are now configured!** 🎉

Push code to your main branch and watch it deploy automatically!
