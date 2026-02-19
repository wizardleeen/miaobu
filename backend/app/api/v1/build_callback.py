"""
Internal build callback API — receives status updates from GitHub Actions builds.

Authentication: HMAC-SHA256 signature in X-Miaobu-Signature header.
The signature is computed over the raw request body using the shared
MIAOBU_CALLBACK_SECRET.
"""
import hmac
import hashlib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from ...config import get_settings
from ...models import Deployment, DeploymentStatus, EnvironmentVariable

router = APIRouter(prefix="/internal", tags=["Internal"])


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_callback_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature from GitHub Actions."""
    settings = get_settings()
    secret = settings.miaobu_callback_secret
    if not secret or not signature:
        return False

    if signature.startswith("sha256="):
        signature = signature[7:]

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def verify_signature(
    request: Request,
    x_miaobu_signature: Optional[str] = Header(None, alias="X-Miaobu-Signature"),
):
    """FastAPI dependency that enforces callback signature.

    For POST: HMAC is computed over the raw request body.
    For GET:  HMAC is computed over the URL path (e.g. /api/v1/internal/deployments/42/env-vars).
    """
    body = await request.body()
    # For GET requests with no body, sign the path instead
    sign_data = body if body else request.url.path.encode()
    if not _verify_callback_signature(sign_data, x_miaobu_signature or ""):
        raise HTTPException(status_code=401, detail="Invalid callback signature")
    request.state.raw_body = body


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class BuildCallbackRequest(BaseModel):
    deployment_id: int
    status: str  # "building", "uploading", "uploaded", "failed"
    build_logs: Optional[str] = None
    error_message: Optional[str] = None
    oss_key: Optional[str] = None  # Python only — OSS key of uploaded zip
    build_time_seconds: Optional[int] = None


class BuildLogsRequest(BaseModel):
    deployment_id: int
    logs: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/build-callback")
async def build_callback(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(verify_signature),
):
    """
    Receive build status updates from GitHub Actions.

    status transitions:
      - "building"  → update to BUILDING, append logs
      - "uploading" → update to UPLOADING, append logs
      - "uploaded"  → set DEPLOYING (ECS deploy worker handles the rest)
      - "failed"    → mark FAILED, store error
    """
    import json
    payload = BuildCallbackRequest(**json.loads(request.state.raw_body))

    deployment = db.query(Deployment).filter(
        Deployment.id == payload.deployment_id
    ).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    # Append logs if provided
    if payload.build_logs:
        deployment.build_logs = (deployment.build_logs or "") + payload.build_logs
        db.commit()

    if payload.status == "building":
        deployment.status = DeploymentStatus.BUILDING
        db.commit()
        return {"ok": True}

    if payload.status == "uploading":
        deployment.status = DeploymentStatus.UPLOADING
        db.commit()
        return {"ok": True}

    if payload.status == "uploaded":
        # Idempotency guard: if already deploying or deployed, return OK
        if deployment.status in (DeploymentStatus.DEPLOYING, DeploymentStatus.DEPLOYED):
            return {"ok": True}

        # Record build time
        if payload.build_time_seconds is not None:
            deployment.build_time_seconds = payload.build_time_seconds
        db.commit()

        # Run deploy inline — FC updates are ~300ms, total <2s
        from ...services.deploy import deploy_static, deploy_python, deploy_node

        project = deployment.project
        project_type = project.project_type or "static"

        if project_type == "python":
            result = deploy_python(deployment.id, payload.oss_key, db)
        elif project_type == "node":
            result = deploy_node(deployment.id, payload.oss_key, db)
        else:
            result = deploy_static(deployment.id, db)

        if not result.get("success"):
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = result.get("error", "Deploy failed")
            db.commit()

        return {"ok": True}

    if payload.status == "failed":
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = payload.error_message or "Build failed"
        if payload.build_time_seconds is not None:
            deployment.build_time_seconds = payload.build_time_seconds
        db.commit()
        return {"ok": True}

    raise HTTPException(status_code=400, detail=f"Unknown status: {payload.status}")


@router.get("/deployments/{deployment_id}/env-vars")
async def get_deployment_env_vars(
    deployment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(verify_signature),
):
    """
    Return decrypted environment variables for a deployment's project.

    Called by GitHub Actions before running the build so env vars can be
    injected into the build environment.
    """
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id
    ).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    from ...services.encryption import decrypt_value

    records = (
        db.query(EnvironmentVariable)
        .filter(EnvironmentVariable.project_id == deployment.project_id)
        .all()
    )

    env_vars = {}
    for rec in records:
        try:
            env_vars[rec.key] = decrypt_value(rec.value)
        except Exception:
            env_vars[rec.key] = rec.value

    return {"env_vars": env_vars}


@router.get("/deployments/{deployment_id}/clone-token")
async def get_clone_token(
    deployment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(verify_signature),
):
    """
    Return the project owner's GitHub OAuth token for cloning.

    Called by GitHub Actions to checkout user repos using the token
    the user already granted during GitHub OAuth login (repo scope).
    This avoids requiring users to create separate PATs.
    """
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id
    ).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    user = deployment.project.user
    if not user or not user.github_access_token:
        raise HTTPException(status_code=404, detail="No GitHub token available")

    return {"token": user.github_access_token}


@router.post("/build-logs")
async def append_build_logs(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(verify_signature),
):
    """
    Append build logs for real-time streaming.

    Called periodically by GitHub Actions during the build.
    """
    import json
    payload = BuildLogsRequest(**json.loads(request.state.raw_body))

    deployment = db.query(Deployment).filter(
        Deployment.id == payload.deployment_id
    ).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    deployment.build_logs = (deployment.build_logs or "") + payload.logs
    db.commit()

    return {"ok": True}
