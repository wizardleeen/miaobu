import hmac
import hashlib
from fastapi import APIRouter, Depends, Request, Header, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from ...database import get_db
from ...models import Project, Deployment, DeploymentStatus
from ...core.exceptions import NotFoundException, BadRequestException

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC SHA256.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value (e.g., "sha256=...")
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not signature.startswith("sha256="):
        return False

    # Extract the hash from signature
    expected_signature = signature.split("=", 1)[1]

    # Calculate HMAC SHA256
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    calculated_signature = mac.hexdigest()

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(calculated_signature, expected_signature)


@router.post("/github/{project_id}")
async def github_webhook(
    project_id: int,
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    db: Session = Depends(get_db)
):
    """
    GitHub webhook endpoint for automatic deployments.

    Handles push events and triggers deployments automatically.
    """
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException(f"Project {project_id} not found")

    # Verify webhook secret
    if not project.webhook_secret:
        raise HTTPException(status_code=400, detail="Webhook not configured for this project")

    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    if not verify_github_signature(body, x_hub_signature_256 or "", project.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse JSON payload
    payload = await request.json()

    # Handle different event types
    if x_github_event == "ping":
        # GitHub sends a ping event to verify webhook is set up correctly
        return {
            "status": "ok",
            "message": "Webhook received and verified",
            "project_id": project_id,
        }

    if x_github_event != "push":
        # Ignore non-push events
        return {
            "status": "ignored",
            "message": f"Event type '{x_github_event}' is not handled",
        }

    # Extract push event data
    ref = payload.get("ref", "")  # e.g., "refs/heads/main"
    branch = ref.replace("refs/heads/", "")

    # Filter: Only deploy if push is to the default branch
    if branch != project.default_branch:
        return {
            "status": "ignored",
            "message": f"Push to '{branch}' ignored (only '{project.default_branch}' triggers deployment)",
        }

    # Extract commit info
    head_commit = payload.get("head_commit", {})
    commit_sha = head_commit.get("id")
    commit_message = head_commit.get("message", "")
    commit_author = head_commit.get("author", {}).get("name", "")

    if not commit_sha:
        raise BadRequestException("No commit SHA found in push event")

    # Check if deployment for this commit already exists
    existing = db.query(Deployment).filter(
        Deployment.project_id == project_id,
        Deployment.commit_sha == commit_sha
    ).first()

    if existing:
        return {
            "status": "skipped",
            "message": f"Deployment for commit {commit_sha[:7]} already exists",
            "deployment_id": existing.id,
        }

    # Create deployment
    deployment = Deployment(
        project_id=project_id,
        commit_sha=commit_sha,
        commit_message=commit_message,
        commit_author=commit_author,
        branch=branch,
        status=DeploymentStatus.QUEUED,
    )

    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Dispatch build via GitHub Actions
    try:
        from ...services.github_actions import trigger_build

        result = await trigger_build(project, deployment)
        if not result["success"]:
            raise Exception(result["error"])
    except Exception as e:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"Failed to dispatch build: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to dispatch build: {str(e)}")

    return {
        "status": "success",
        "message": f"Deployment triggered for commit {commit_sha[:7]}",
        "deployment_id": deployment.id,
        "commit_sha": commit_sha,
        "commit_message": commit_message,
        "branch": branch,
    }


@router.post("/projects/{project_id}/setup")
async def setup_webhook(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Set up GitHub webhook for a project.

    This endpoint is called internally when importing a repository.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException(f"Project {project_id} not found")

    # Check if webhook already exists
    if project.webhook_id and project.webhook_secret:
        return {
            "status": "already_configured",
            "message": "Webhook is already configured for this project",
            "webhook_id": project.webhook_id,
        }

    from ...services.github import GitHubService
    from ...config import get_settings
    import secrets

    settings = get_settings()

    # Generate webhook secret
    webhook_secret = secrets.token_urlsafe(32)

    # Construct webhook URL
    webhook_url = f"{settings.backend_url}/api/v1/webhooks/github/{project_id}"

    # Get user for access token
    user = project.user

    # Extract owner and repo from github_repo_name (format: "owner/repo")
    owner, repo = project.github_repo_name.split("/")

    try:
        # Create webhook on GitHub
        webhook = await GitHubService.create_webhook(
            user.github_access_token,
            owner,
            repo,
            webhook_url,
            webhook_secret
        )

        # Save webhook info to project
        project.webhook_id = webhook["id"]
        project.webhook_secret = webhook_secret
        db.commit()

        return {
            "status": "success",
            "message": "Webhook created successfully",
            "webhook_id": webhook["id"],
            "webhook_url": webhook_url,
        }

    except Exception as e:
        raise BadRequestException(f"Failed to create webhook: {str(e)}")


@router.delete("/projects/{project_id}/webhook")
async def delete_webhook(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete GitHub webhook for a project.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException(f"Project {project_id} not found")

    if not project.webhook_id:
        return {
            "status": "not_configured",
            "message": "No webhook configured for this project",
        }

    from ...services.github import GitHubService

    # Get user for access token
    user = project.user

    # Extract owner and repo
    owner, repo = project.github_repo_name.split("/")

    try:
        # Delete webhook from GitHub
        success = await GitHubService.delete_webhook(
            user.github_access_token,
            owner,
            repo,
            project.webhook_id
        )

        if success:
            # Clear webhook info from project
            project.webhook_id = None
            project.webhook_secret = None
            db.commit()

            return {
                "status": "success",
                "message": "Webhook deleted successfully",
            }
        else:
            return {
                "status": "failed",
                "message": "Failed to delete webhook from GitHub",
            }

    except Exception as e:
        raise BadRequestException(f"Failed to delete webhook: {str(e)}")
