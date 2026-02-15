from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from celery import Celery
import os

from ...database import get_db
from ...models import User, Project, Deployment
from ...schemas import DeploymentCreate, DeploymentResponse
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException

router = APIRouter(prefix="/deployments", tags=["Deployments"])

# Initialize Celery client for sending tasks
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
celery_app = Celery('miaobu-worker', broker=REDIS_URL, backend=REDIS_URL)


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

    # Queue Celery task for building and deploying
    try:
        task = celery_app.send_task(
            'tasks.build.build_and_deploy',
            args=[deployment.id],
            queue='builds'
        )
        deployment.celery_task_id = task.id
        db.commit()
    except Exception as e:
        print(f"Failed to queue build task: {e}")
        # Don't fail the request, just log the error

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
