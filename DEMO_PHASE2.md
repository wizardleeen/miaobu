# Phase 2 Demo Guide

This guide walks through the new GitHub integration features.

## Prerequisites

1. Services running: `docker-compose up -d`
2. Logged in with GitHub account
3. Have at least one repository on GitHub

## Demo Flow

### 1. Import a Repository

**Navigate to Import:**
```
Dashboard → Projects → "Import from GitHub"
or
http://localhost:5173/projects/import
```

**What You'll See:**
- List of all your GitHub repositories
- Search bar to filter repositories
- Repository cards showing:
  - Repository name and description
  - Primary language
  - Last update date
  - "Already Imported" badge (if applicable)
  - Private repository badge

**Try This:**
1. Scroll through your repositories
2. Use the search bar to find a specific repo
3. Notice which ones are already imported (grayed out)

### 2. Analyze a Repository

**Select Repository:**
- Click on any repository card that isn't already imported

**What Happens:**
- Shows "Analyzing repository..." spinner
- Backend fetches package.json
- Detects framework and build configuration
- Analyzes repository structure

**Analysis Results Show:**
- **Detected Framework**: e.g., "vite", "next", "create-react-app"
- **Confidence Level**: High/Medium/Low
- **Package Manager**: npm/yarn/pnpm
- **Build Configuration**:
  - Build command
  - Install command
  - Output directory
  - Node version
- **Repository Details**:
  - TypeScript support
  - Test files present
  - Docker configuration
  - Lock file type

### 3. Customize Configuration

**Editable Fields:**
- Project name
- Build command
- Install command
- Output directory
- Node version (dropdown: 16, 18, 20)

**Try This:**
1. Change the project name
2. Modify the build command
3. Adjust the output directory
4. Select different Node version

**Example Customization:**
```
Project Name: "My Awesome App"
Build Command: "npm run build:production"
Output Directory: "build"
Node Version: "20"
```

### 4. Import the Repository

**Click "Import Repository"**

**What Happens:**
1. Button shows "Importing..." state
2. Backend creates project with configuration
3. Generates unique slug (URL-safe name)
4. Creates default domain: `{slug}.miaobu.app`
5. Saves to database
6. Redirects to project detail page

**Result:**
- Project is now listed in your projects
- Has auto-generated domain
- Ready for deployment (Phase 3)

### 5. Manage Project Settings

**Navigate to Settings:**
```
Projects → Select Project → "Settings" button
or
http://localhost:5173/projects/{id}/settings
```

**Settings Page Sections:**

#### General
- Project name (editable)
- Slug (read-only, unique identifier)
- Default domain (read-only, with "Visit" link)

#### Build Configuration
- Build command
- Install command
- Output directory
- Node version

#### Git Repository
- Repository name (with GitHub link)
- Default branch (read-only)

#### Danger Zone
- Delete project (requires two confirmations)

**Try This:**
1. Update the build command
2. Change the Node version
3. Click "Save Changes"
4. Navigate back to project detail
5. Verify changes are reflected

### 6. Delete a Project (Optional)

**Warning: This is permanent!**

1. Scroll to "Danger Zone"
2. Click "Delete Project"
3. Read the confirmation warning
4. Click "Confirm Delete"
5. Redirected to projects list

## Example Repositories to Test

### Vite React Project
Will detect:
- Framework: `vite`
- Build: `npm run build`
- Output: `dist`
- Confidence: High

### Create React App
Will detect:
- Framework: `create-react-app`
- Build: `npm run build`
- Output: `build`
- Confidence: High

### Next.js Project
Will detect:
- Framework: `next`
- Build: `npm run build && npm run export`
- Output: `out`
- Note: Requires static export

### Unknown/Generic Project
No package.json or unrecognized:
- Framework: `unknown`
- Build: `npm run build`
- Output: `dist`
- Confidence: Low

## Testing Different Scenarios

### Scenario 1: TypeScript Project
Repository with `tsconfig.json`:
- ✓ TypeScript: Yes
- Auto-detects from config files

### Scenario 2: Monorepo
Repository with multiple package.json files:
- Analyzes root package.json
- May need manual configuration

### Scenario 3: Custom Build Setup
Non-standard build configuration:
- Use "Manual Import" option on Projects page
- Fill in all fields manually

### Scenario 4: Already Imported
Repository already exists as project:
- Shows "Already Imported" badge
- Cannot click to select
- Must delete existing project first to re-import

## API Testing with Swagger

Access API documentation:
```
http://localhost:8000/docs
```

**Test Endpoints:**

1. **List Repositories**
   ```
   GET /api/v1/repositories
   Query params: page=1, per_page=30, search=optional
   ```

2. **Analyze Repository**
   ```
   GET /api/v1/repositories/{owner}/{repo}/analyze
   Query params: branch=main (optional)
   ```

3. **Import Repository**
   ```
   POST /api/v1/repositories/{owner}/{repo}/import
   Body: {
     "branch": "main",
     "custom_config": {
       "name": "Custom Name",
       "build_command": "npm run build"
     }
   }
   ```

## Troubleshooting

### Repository List Empty
- Check GitHub OAuth token has repo scope
- Verify GitHub account has repositories
- Check browser console for errors

### Analysis Fails
- Repository may be private without access
- GitHub API rate limit reached
- No package.json in repository (expected for non-Node projects)

### Import Fails
- Repository already imported (check projects list)
- Invalid build configuration
- Database connection issue

### Settings Not Saving
- Check backend logs: `docker-compose logs backend`
- Verify authentication token
- Check form validation errors

## Next Steps

After exploring Phase 2:
- **Phase 3**: Build system will execute the configured build commands
- **Phase 4**: OSS deployment will upload built files to Alibaba Cloud
- **Phase 5**: CDN will serve your deployed site

For now, you can:
- Import multiple repositories
- Configure build settings
- Organize your projects
- Prepare for automatic deployments in Phase 3

---

**Happy Testing!** 🚀
