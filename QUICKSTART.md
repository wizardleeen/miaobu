# Miaobu - Quick Start Guide

This guide will help you get Miaobu up and running locally.

## Prerequisites

- Docker and Docker Compose installed
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)
- GitHub account for OAuth setup
- Alibaba Cloud account (for deployment features)

## Initial Setup

### 1. Configure GitHub OAuth

First, create a GitHub OAuth application:

1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in the details:
   - Application name: `Miaobu Local`
   - Homepage URL: `http://localhost:5173`
   - Authorization callback URL: `http://localhost:8000/api/v1/auth/github/callback`
4. Click "Register application"
5. Copy the Client ID and generate a Client Secret

### 2. Update Environment Variables

Edit the `.env` file and update the following:

```bash
# Replace these with your GitHub OAuth app credentials
GITHUB_CLIENT_ID=your-actual-client-id
GITHUB_CLIENT_SECRET=your-actual-client-secret

# Generate a secure JWT secret (you can use: openssl rand -hex 32)
JWT_SECRET_KEY=your-secure-random-secret-key

# Optional: Update Aliyun credentials if you want to test deployment features
ALIYUN_ACCESS_KEY_ID=your-aliyun-key
ALIYUN_ACCESS_KEY_SECRET=your-aliyun-secret
```

### 3. Start the Application

Run the setup script:

```bash
./scripts/setup.sh
```

This will:
- Start PostgreSQL and Redis
- Build the backend Docker image
- Run database migrations
- Start all services

### 4. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Usage

### Sign In

1. Go to http://localhost:5173
2. Click "Sign In"
3. Authenticate with GitHub
4. You'll be redirected to the dashboard

### Create a Project

1. Go to Projects page
2. Click "New Project"
3. Fill in the form:
   - Project name
   - GitHub repository (format: owner/repo)
   - Repository URL
   - Repository ID (find this via GitHub API)
   - Build settings (or use defaults)
4. Click "Create Project"

### Manual Deployment (Coming in Phase 3)

Currently, the deployment pipeline is not yet implemented. This will be added in Phase 3 of the implementation.

## Development

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f worker
```

### Stop Services

```bash
docker-compose down
```

### Reset Database

```bash
./scripts/reset-db.sh
```

### Local Development (without Docker)

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

#### Worker

```bash
cd worker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
celery -A celery_app worker --loglevel=info
```

## Troubleshooting

### Docker containers won't start

```bash
# Check Docker is running
docker info

# Check container logs
docker-compose logs

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

### Database migration errors

```bash
# Reset database
./scripts/reset-db.sh

# Or manually run migrations
docker-compose run --rm backend alembic upgrade head
```

### Frontend can't connect to backend

- Check that backend is running: `curl http://localhost:8000/health`
- Verify VITE_API_URL in frontend environment
- Check CORS settings in backend

## Next Steps

Once Phase 1 is working:

1. **Phase 2**: Implement GitHub repository import with auto-detection
2. **Phase 3**: Build system with Docker isolation
3. **Phase 4**: OSS deployment
4. **Phase 5**: CDN integration
5. **Phase 6**: Webhook automation
6. **Phase 7**: Custom domains
7. **Phase 8**: SSL automation

## Getting Help

- Check the main [README.md](./README.md) for architecture details
- Review API documentation at http://localhost:8000/docs
- Check Docker logs for error messages
- Ensure all environment variables are properly configured
