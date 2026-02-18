from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ...database import get_db
from ...models import User, Project, Deployment
from ...schemas import DeploymentCreate, DeploymentResponse
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException

router = APIRouter(prefix="/deployments", tags=["Deployments"])


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_data: DeploymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create and trigger a new deployment."""
    # Verify project exists and user has access
    project = db.query(Project).filter(Project.id == deployment_data.project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    # Create deployment record
    deployment = Deployment(
        project_id=project.id,
        commit_sha=deployment_data.commit_sha,
        commit_message=deployment_data.commit_message,
        commit_author=deployment_data.commit_author,
        branch=deployment_data.branch,
    )

    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Dispatch build via GitHub Actions
    try:
        from ...services.github_actions import trigger_build
        import asyncio

        result = await trigger_build(deployment.project, deployment)
        if not result["success"]:
            print(f"Failed to dispatch build: {result['error']}")
    except Exception as e:
        print(f"Failed to dispatch build: {e}")

    return deployment


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific deployment."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()

    if not deployment:
        raise NotFoundException("Deployment not found")

    # Check user has access via project
    if deployment.project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this deployment")

    return deployment


@router.get("/project/{project_id}", response_model=List[DeploymentResponse])
async def list_project_deployments(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all deployments for a project."""
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    deployments = db.query(Deployment).filter(
        Deployment.project_id == project_id
    ).order_by(Deployment.created_at.desc()).all()

    return deployments


@router.get("/{deployment_id}/logs")
async def get_deployment_logs(
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get deployment build logs."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()

    if not deployment:
        raise NotFoundException("Deployment not found")

    if deployment.project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this deployment")

    return {
        "deployment_id": deployment.id,
        "status": deployment.status,
        "logs": deployment.build_logs or "",
        "error_message": deployment.error_message
    }
