from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timezone

from .config import get_settings
from .api.v1 import auth, projects, deployments, repositories, projects_deploy, webhooks, env_vars, build_callback, api_tokens
from .api.v1 import domains_esa as domains
from .api.v1.public.router import router as public_router
from .schemas import HealthCheck

settings = get_settings()

app = FastAPI(
    title="Miaobu API",
    description="Deployment platform API",
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


# Public API structured error handler
from fastapi.exceptions import HTTPException as FastAPIHTTPException


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Return structured errors for public API paths, default for others."""
    if request.url.path.startswith("/api/v1/public/"):
        code_map = {400: "bad_request", 401: "unauthorized", 403: "forbidden",
                    404: "not_found", 409: "conflict", 422: "validation_error", 429: "rate_limited"}
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {
                "code": code_map.get(exc.status_code, "error"),
                "message": exc.detail,
            }},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled exceptions."""
    if request.url.path.startswith("/api/v1/public/"):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc) if settings.environment == "development" else None
        }
    )


# Rate limit placeholder headers for public API
class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/public/"):
            response.headers["X-RateLimit-Limit"] = "1000"
            response.headers["X-RateLimit-Remaining"] = "999"
            response.headers["X-RateLimit-Reset"] = str(int(datetime.now(timezone.utc).timestamp()) + 3600)
        return response


app.add_middleware(RateLimitHeaderMiddleware)


# Health check endpoint
@app.get("/health", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck(status="ok", timestamp=datetime.now(timezone.utc))


# API routes
app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(deployments.router, prefix="/api/v1")
app.include_router(repositories.router, prefix="/api/v1")
app.include_router(projects_deploy.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(domains.router, prefix="/api/v1")
app.include_router(env_vars.router, prefix="/api/v1")
app.include_router(build_callback.router, prefix="/api/v1")
app.include_router(api_tokens.router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1/public")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Miaobu API",
        "version": "1.0.0",
        "docs": "/docs"
    }
