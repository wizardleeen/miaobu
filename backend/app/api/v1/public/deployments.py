"""Public API — Deployment endpoints."""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from ....database import get_db
from ....models import User, Project, Deployment, DeploymentStatus
from ....core.security import get_current_user_flexible
from ....core.exceptions import NotFoundException, ForbiddenException
from .helpers import PaginationParams, paginated_response, single_response

router = APIRouter(tags=["Public API - Deployments"])


def _deployment_dict(d: Deployment) -> dict:
    """Serialize a Deployment to a public API dict."""
    return {
        "id": d.id,
        "project_id": d.project_id,
        "commit_sha": d.commit_sha,
        "commit_message": d.commit_message,
        "commit_author": d.commit_author,
        "branch": d.branch,
        "status": d.status.value,
        "deployment_url": d.deployment_url,
        "build_time_seconds": d.build_time_seconds,
        "error_message": d.error_message,
        "created_at": d.created_at.isoformat(),
        "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
    }


def _get_user_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


@router.get("/projects/{project_id}/deployments")
async def list_deployments(
    project_id: int,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List deployments for a project."""
    _get_user_project(project_id, current_user, db)

    query = db.query(Deployment).filter(Deployment.project_id == project_id)
    total = query.count()
    deployments = (
        query.order_by(Deployment.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.per_page)
        .all()
    )
    return paginated_response(
        [_deployment_dict(d) for d in deployments],
        total,
        pagination.page,
        pagination.per_page,
    )


@router.get("/projects/{project_id}/deployments/{deployment_id}")
async def get_deployment(
    project_id: int,
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Get a single deployment by ID."""
    _get_user_project(project_id, current_user, db)

    deployment = (
        db.query(Deployment)
        .filter(Deployment.id == deployment_id, Deployment.project_id == project_id)
        .first()
    )
    if not deployment:
        raise NotFoundException("Deployment not found")

    return single_response(_deployment_dict(deployment))


@router.get("/projects/{project_id}/deployments/{deployment_id}/logs")
async def get_deployment_logs(
    project_id: int,
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Get build logs for a deployment."""
    _get_user_project(project_id, current_user, db)

    deployment = (
        db.query(Deployment)
        .filter(Deployment.id == deployment_id, Deployment.project_id == project_id)
        .first()
    )
    if not deployment:
        raise NotFoundException("Deployment not found")

    return single_response({
        "deployment_id": deployment.id,
        "status": deployment.status.value,
        "build_logs": deployment.build_logs,
        "error_message": deployment.error_message,
    })


class TriggerDeploymentBody(BaseModel):
    branch: Optional[str] = Field(None, max_length=100)


@router.post("/projects/{project_id}/deployments", status_code=201)
async def trigger_deployment(
    project_id: int,
    body: TriggerDeploymentBody = TriggerDeploymentBody(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Trigger a new deployment for a project."""
    project = _get_user_project(project_id, current_user, db)

    deploy_branch = body.branch or project.default_branch

    # Get latest commit from GitHub
    try:
        from ....services.github import GitHubService

        owner, repo = project.github_repo_name.split("/")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/branches/{deploy_branch}",
                headers={
                    "Authorization": f"Bearer {current_user.github_access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            branch_data = response.json()
            latest_commit = branch_data["commit"]
            commit_sha = latest_commit["sha"]
            commit_message = latest_commit["commit"]["message"]
            commit_author = latest_commit["commit"]["author"]["name"]
    except Exception:
        commit_sha = "manual"
        commit_message = "Manual deployment triggered via API"
        commit_author = current_user.github_username

    deployment = Deployment(
        project_id=project.id,
        commit_sha=commit_sha,
        commit_message=commit_message,
        commit_author=commit_author,
        branch=deploy_branch,
        status=DeploymentStatus.QUEUED,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Dispatch build via GitHub Actions
    try:
        from ....services.github_actions import trigger_build

        result = await trigger_build(project, deployment)
        if not result["success"]:
            raise Exception(result["error"])
    except Exception as e:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"Failed to dispatch build: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

    return single_response(_deployment_dict(deployment))


@router.post("/projects/{project_id}/deployments/{deployment_id}/cancel")
async def cancel_deployment(
    project_id: int,
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Cancel a running deployment."""
    _get_user_project(project_id, current_user, db)

    deployment = (
        db.query(Deployment)
        .filter(Deployment.id == deployment_id, Deployment.project_id == project_id)
        .first()
    )
    if not deployment:
        raise NotFoundException("Deployment not found")

    terminal = {DeploymentStatus.DEPLOYED, DeploymentStatus.FAILED, DeploymentStatus.CANCELLED, DeploymentStatus.PURGED}
    if deployment.status in terminal:
        raise HTTPException(status_code=400, detail=f"Cannot cancel deployment with status {deployment.status.value}")

    deployment.status = DeploymentStatus.CANCELLED
    db.commit()

    return single_response(_deployment_dict(deployment))


@router.post("/projects/{project_id}/deployments/{deployment_id}/rollback")
async def rollback_deployment(
    project_id: int,
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Roll back to a previous deployment."""
    project = _get_user_project(project_id, current_user, db)

    deployment = (
        db.query(Deployment)
        .filter(Deployment.id == deployment_id, Deployment.project_id == project_id)
        .first()
    )
    if not deployment:
        raise NotFoundException("Deployment not found")

    if deployment.status != DeploymentStatus.DEPLOYED:
        raise HTTPException(status_code=400, detail="Only deployed deployments can be used for rollback")

    if project.active_deployment_id == deployment.id:
        raise HTTPException(status_code=400, detail="This deployment is already active")

    # Check no in-progress deployment
    in_progress = (
        db.query(Deployment)
        .filter(
            Deployment.project_id == project.id,
            Deployment.status.in_([
                DeploymentStatus.QUEUED,
                DeploymentStatus.CLONING,
                DeploymentStatus.BUILDING,
                DeploymentStatus.UPLOADING,
                DeploymentStatus.DEPLOYING,
            ]),
        )
        .first()
    )
    if in_progress:
        raise HTTPException(status_code=409, detail="Cannot rollback while a deployment is in progress")

    from ....services.deploy import rollback_to_deployment

    result = rollback_to_deployment(deployment.id, db)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Rollback failed"))

    db.refresh(deployment)
    return single_response(_deployment_dict(deployment))
