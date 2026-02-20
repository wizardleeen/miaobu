# Miaobu 🚀

A complete, production-ready static frontend deployment platform for Alibaba Cloud ecosystem.

**Status: Production Ready** ✅ | **Version: 1.0.0** | **All 9 Phases Complete**

## Features

### ✅ Complete Feature Set (All Phases 1-9)

**Core Features:**
- 🔐 **GitHub OAuth Authentication** - Secure login with GitHub
- 📦 **Automatic Repository Import** - Smart build detection for 10+ frameworks
- 🚀 **Automated Build Pipeline** - Docker-based builds with intelligent caching
- ☁️ **Alibaba Cloud OSS** - Upload builds to OSS with gzip compression
- 🌐 **CDN Integration** - Global content delivery with automatic cache purging
- 🪝 **GitHub Webhooks** - Zero-touch deployments on git push
- 🔄 **Real-time Build Logs** - Watch your builds in real-time
- 📊 **Deployment History** - Track all deployments with full logs
- 🔗 **Custom Domains** - Add your own domains with DNS verification
- 🔒 **SSL Automation** - Free HTTPS via Let's Encrypt with auto-renewal

**Production Features:**
- 🛡️ **Rate Limiting** - Distributed rate limiting with Redis
- 🔐 **Security Hardening** - HTTPS, security headers, input validation
- 📈 **Production Ready** - Complete deployment guide and monitoring
- 📚 **Complete Documentation** - Setup guides, API docs, troubleshooting

## Architecture

- **Backend:** FastAPI (Python)
- **Task Queue:** Celery + Redis
- **Database:** PostgreSQL
- **Frontend:** React + TypeScript + Vite + Tailwind CSS
- **Build Isolation:** Docker containers
- **Storage:** Alibaba Cloud OSS
- **CDN:** Alibaba Cloud CDN

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd miaobu
```

2. Copy environment file and configure:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Start the development environment:
```bash
docker-compose up -d
```

4. Run database migrations:
```bash
docker-compose exec backend alembic upgrade head
```

5. Access the application:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

### Worker Development

```bash
cd worker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
celery -A celery_app worker --loglevel=info
```

## Project Structure

```
miaobu/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── api/v1/      # API endpoints
│   │   ├── models/      # Database models
│   │   ├── services/    # Business logic
│   │   └── core/        # Security and config
│   └── alembic/         # Database migrations
├── worker/               # Celery workers
│   ├── tasks/           # Async tasks
│   └── builders/        # Docker build isolation
├── frontend/             # React SPA
│   └── src/
│       ├── pages/       # Page components
│       ├── components/  # Reusable components
│       └── services/    # API client
└── infrastructure/       # Docker Compose and configs
```

## Documentation

- [Quick Start Guide](QUICKSTART.md) - Get started in 5 minutes
- [OSS Setup Guide](OSS_SETUP_GUIDE.md) - Configure Alibaba Cloud OSS
- [CDN Setup Guide](CDN_SETUP_GUIDE.md) - Set up CDN for global delivery
- [Webhook Setup Guide](WEBHOOK_SETUP_GUIDE.md) - Enable auto-deployments
- **Phase Summaries:**
  - [Phase 2: GitHub Integration](PHASE2_SUMMARY.md)
  - [Phase 3: Build System](PHASE3_SUMMARY.md)
  - [Phase 4: OSS Deployment](PHASE4_SUMMARY.md)
  - [Phase 5: CDN Integration](PHASE5_SUMMARY.md)
  - [Phase 6: Webhook Automation](PHASE6_SUMMARY.md)
  - [Phase 7: Custom Domains](PHASE7_SUMMARY.md)
  - [Phase 8: SSL Automation](PHASE8_SUMMARY.md)
  - [Phase 9: Production Polish](PHASE9_SUMMARY.md)
- **Production Guides:**
  - [Production Checklist](PRODUCTION_CHECKLIST.md)
  - [Deployment Guide](DEPLOYMENT_GUIDE.md)
- **Testing Guides:**
  - [Testing Phase 3](TESTING_PHASE3.md)
  - [Testing Phase 6](TESTING_PHASE6.md)

## Current Status

**🎉 PROJECT COMPLETE - ALL 9 PHASES FINISHED! 🎉**

✅ **Phases 1-9 fully implemented and production-ready**

**What's included:**
- ✅ Complete build and deployment pipeline
- ✅ CDN integration with cache management
- ✅ Automatic deployments via webhooks
- ✅ Custom domain support with DNS verification
- ✅ Free SSL certificates with automatic renewal
- ✅ Production-grade security and monitoring
- ✅ Comprehensive documentation

**Ready for production deployment!** 🚀

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) to deploy your own instance.

## License

MIT
# Test commit to trigger deployment
