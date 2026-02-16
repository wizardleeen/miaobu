from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime

from .config import get_settings
from .api.v1 import auth, projects, deployments, repositories, projects_deploy, webhooks
from .api.v1 import domains_esa as domains
from .schemas import HealthCheck

settings = get_settings()

app = FastAPI(
    title="Miaobu API",
    description="Static frontend deployment platform for Alibaba Cloud",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
# Allow multiple frontend origins for development and production
allowed_origins = [
    settings.frontend_url,
    "http://localhost:5173",
    "https://app.metavm.tech",
    "https://miaobu.metavm.tech",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.environment == "development" else None
        }
    )


# Health check endpoint
@app.get("/health", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck(status="ok", timestamp=datetime.utcnow())


# API routes
app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(deployments.router, prefix="/api/v1")
app.include_router(repositories.router, prefix="/api/v1")
app.include_router(projects_deploy.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(domains.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Miaobu API",
        "version": "1.0.0",
        "docs": "/docs"
    }
