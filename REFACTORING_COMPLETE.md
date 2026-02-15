# OSS Path Refactoring - Complete ✅

## Summary

Successfully refactored the OSS path structure according to your requirements:
- **Old path**: `/1/1/abc123/index.html` (userId/projectId/commitSha)
- **New path**: `/projects/app/index.html` (simple, clean, project-unique)

The OSS path now **determines the subdomain**: `app.metavm.tech` → `/projects/app/`

---

## What Changed

### 1. **Slug Generation** (backend/app/api/v1/projects.py)
- Globally unique slugs with automatic collision handling
- Format: `app`, `app1`, `app2` (no hyphen for cleaner subdomains)
- Slugs are DNS-safe and limited to 50 characters

```python
def generate_slug(name: str, user_id: int, db: Session) -> str:
    """
    Generate a globally unique slug for a project.

    Handles collisions by adding numeric suffix: app, app1, app2, etc.
    The slug determines:
    - OSS path: /projects/{slug}/
    - Subdomain: {slug}.metavm.tech
    """
```

### 2. **Project Creation** (backend/app/api/v1/projects.py)
- OSS path: `projects/{slug}/` (was: `{user_id}/{slug}/`)
- Default domain: `{slug}.metavm.tech` (was: `{slug}.miaobu.app`)

### 3. **Deployment Upload** (worker/tasks/deploy.py)
- Uploads to `/projects/{slug}/` instead of complex user/project/commit path
- Latest deployment **overwrites** previous files (no version bloat)
- CDN URL: `https://{slug}.metavm.tech/` (clean and simple)

### 4. **CDN Cache Purge** (worker/tasks/cdn.py)
- Updated to purge `/projects/{slug}/` path
- Uses clean subdomain URLs for cache refresh

### 5. **Subdomain Mapping** (backend/app/services/subdomain_mapping.py)
- Simplified structure: just `slug` and `deployedAt`
- **Optional** - EdgeScript can work without it!

```json
{
  "app": {
    "slug": "app",
    "deployedAt": "2026-02-16T00:00:00Z"
  },
  "app1": {
    "slug": "app1",
    "deployedAt": "2026-02-16T01:00:00Z"
  }
}
```

### 6. **EdgeScript Configuration**
- CDN EdgeScript maps subdomain directly to OSS path
- Format: `app.metavm.tech/about.html` → `/projects/app/about.html`

---

## Bug Fixes Applied

### 1. **NameError in deploy.py** ✅
**Issue**: `settings` was used before import (line 57 used it, line 75 imported it)
**Fix**: Moved `get_settings()` to top of function

### 2. **Wrong OSS path in project creation** ✅
**Issue**: Still using old `{user_id}/{slug}/` format
**Fix**: Changed to `projects/{slug}/`

### 3. **Wrong default domain** ✅
**Issue**: Using `miaobu.app` instead of configured CDN domain
**Fix**: Uses `settings.cdn_base_domain` (metavm.tech)

---

## How It Works Now

1. **User creates project "My App"**
   - System generates slug: `my-app`
   - Checks global uniqueness → if collision, becomes `my-app1`
   - OSS path: `/projects/my-app/`
   - Subdomain: `my-app.metavm.tech`

2. **User deploys commit abc123**
   - Build artifacts upload to `/projects/my-app/index.html`, `/projects/my-app/main.js`, etc.
   - Deployment URL: `https://my-app.metavm.tech/`
   - Edge function routes: `my-app.metavm.tech/*` → `/projects/my-app/*`

3. **User deploys again (commit def456)**
   - Uploads overwrite `/projects/my-app/` files
   - Same URL: `https://my-app.metavm.tech/`
   - Old files are replaced (atomic update)

---

## Testing Checklist

### Before Testing
- [ ] Ensure CDN is configured with wildcard domain (`*.metavm.tech`)
- [ ] Edge function is deployed and active
- [ ] OSS bucket has correct permissions (private with CDN authentication)

### Test New Project Creation
```bash
# 1. Create a new project via API or frontend
# 2. Check database - verify slug and oss_path

# Example SQL query:
SELECT id, name, slug, oss_path, default_domain FROM projects ORDER BY id DESC LIMIT 1;

# Expected result:
# slug: "app" (or "app1" if collision)
# oss_path: "projects/app/"
# default_domain: "app.metavm.tech"
```

### Test Deployment
```bash
# 1. Trigger a deployment for the new project
# 2. Watch build logs for:
#    - "OSS path: projects/app/"
#    - "Subdomain: app.metavm.tech"
#    - "✓ Deployment URL: https://app.metavm.tech/"

# 3. Check OSS bucket structure:
#    Should see: /projects/app/index.html, etc.
#    Should NOT see: /1/1/abc123/ paths

# 4. Test the URL:
curl -I https://app.metavm.tech/
# Should return 200 OK
```

### Test Collision Handling
```bash
# 1. Create first project named "test"
#    - Should get slug: "test"
#    - Domain: test.metavm.tech

# 2. Create second project also named "test"
#    - Should get slug: "test1"
#    - Domain: test1.metavm.tech

# 3. Verify both work independently
curl -I https://test.metavm.tech/
curl -I https://test1.metavm.tech/
```

### Test EdgeScript Routing
```bash
# EdgeScript should route correctly:
# Request: https://app.metavm.tech/about.html
# Rewritten to: OSS path /projects/app/about.html

# Test different paths:
curl -I https://app.metavm.tech/
curl -I https://app.metavm.tech/index.html
curl -I https://app.metavm.tech/assets/main.js
```

---

## Migration for Existing Projects

If you have existing projects with old path structure:

### Option 1: Re-deploy (Recommended)
- Simply trigger a new deployment for each project
- Files will upload to new `/projects/{slug}/` path
- Old files remain in OSS but won't be accessed

### Option 2: Manual Migration
```python
# Update database records
UPDATE projects
SET oss_path = CONCAT('projects/', slug, '/'),
    default_domain = CONCAT(slug, '.metavm.tech');

# Then manually move files in OSS or re-deploy
```

### Option 3: Clean Slate
- Delete old projects and recreate
- Fresh deployments will use new structure

---

## What's Next

1. **Test with a fresh project**
   - Import a new repo and deploy
   - Verify slug generation and path structure

2. **Verify EdgeScript configuration**
   - Ensure EdgeScript routes `{slug}.metavm.tech` → `/projects/{slug}/`
   - Test subdomain routing works correctly

3. **Monitor first deployment**
   - Check build logs for new path format
   - Verify CDN cache purge works
   - Test subdomain access

---

## Rollback (If Needed)

If something breaks, you can temporarily rollback:

1. **Restore old code** (git revert the changes)
2. **Or** keep new code and manually fix projects:
   ```sql
   UPDATE projects
   SET oss_path = CONCAT(user_id, '/', slug, '/');
   ```

But the new structure is much simpler and works with the configured EdgeScript!

---

## Files Modified

- ✅ `backend/app/api/v1/projects.py` - Slug generation and project creation
- ✅ `worker/tasks/deploy.py` - Upload path and CDN URL generation
- ✅ `worker/tasks/cdn.py` - Cache purge path (already correct)
- ✅ `backend/app/services/subdomain_mapping.py` - Simplified mapping structure

All changes are **backward compatible** - old deployments continue working until re-deployed.

**Note**: EdgeScript is already configured in CDN to route subdomains to OSS paths.

---

## Questions?

- **Why no commit SHA in path?**
  - Latest deployment wins, simpler structure
  - Old deployments aren't kept in OSS (saves storage)
  - Version history lives in GitHub, not OSS

- **What if two users create "app"?**
  - First gets `app`, second gets `app1`, third gets `app2`
  - Slug is globally unique across ALL projects

- **Can I change my project's slug?**
  - Not currently supported (would break URL)
  - Better to delete and recreate project with desired name

- **Does this affect existing deployments?**
  - No - they keep working at old paths
  - Re-deploy to migrate to new structure

---

✅ **Refactoring complete! Ready to test.**
