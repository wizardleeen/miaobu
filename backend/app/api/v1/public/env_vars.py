"""Public API — Environment Variable endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List

from ....database import get_db
from ....models import User, Project, EnvironmentVariable
from ....core.security import get_current_user_flexible
from ....core.exceptions import NotFoundException, ForbiddenException
from .helpers import single_response

router = APIRouter(tags=["Public API - Environment Variables"])

MASK = "••••••••"


def _get_user_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


def _env_var_dict(ev: EnvironmentVariable) -> dict:
    value = MASK if ev.is_secret else ev.value
    if not ev.is_secret:
        try:
            from ....services.encryption import decrypt_value
            value = decrypt_value(ev.value)
        except Exception:
            value = ev.value

    return {
        "id": ev.id,
        "project_id": ev.project_id,
        "key": ev.key,
        "value": value,
        "is_secret": ev.is_secret,
        "created_at": ev.created_at.isoformat(),
        "updated_at": ev.updated_at.isoformat(),
    }


@router.get("/projects/{project_id}/env-vars")
async def list_env_vars(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List environment variables for a project. Secret values are masked."""
    _get_user_project(project_id, current_user, db)

    env_vars = (
        db.query(EnvironmentVariable)
        .filter(EnvironmentVariable.project_id == project_id)
        .order_by(EnvironmentVariable.key)
        .all()
    )
    return {"data": [_env_var_dict(ev) for ev in env_vars]}


class CreateEnvVarBody(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str
    is_secret: bool = False


@router.post("/projects/{project_id}/env-vars", status_code=201)
async def create_env_var(
    project_id: int,
    body: CreateEnvVarBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Create a new environment variable."""
    _get_user_project(project_id, current_user, db)

    existing = (
        db.query(EnvironmentVariable)
        .filter(EnvironmentVariable.project_id == project_id, EnvironmentVariable.key == body.key)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Environment variable '{body.key}' already exists")

    from ....services.encryption import encrypt_value

    env_var = EnvironmentVariable(
        project_id=project_id,
        key=body.key,
        value=encrypt_value(body.value),
        is_secret=body.is_secret,
    )
    db.add(env_var)
    db.commit()
    db.refresh(env_var)

    return single_response({
        "id": env_var.id,
        "project_id": env_var.project_id,
        "key": env_var.key,
        "value": MASK if env_var.is_secret else body.value,
        "is_secret": env_var.is_secret,
        "created_at": env_var.created_at.isoformat(),
        "updated_at": env_var.updated_at.isoformat(),
    })


@router.delete("/projects/{project_id}/env-vars/{var_id}", status_code=204)
async def delete_env_var(
    project_id: int,
    var_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Delete an environment variable."""
    _get_user_project(project_id, current_user, db)

    env_var = (
        db.query(EnvironmentVariable)
        .filter(EnvironmentVariable.id == var_id, EnvironmentVariable.project_id == project_id)
        .first()
    )
    if not env_var:
        raise NotFoundException("Environment variable not found")

    db.delete(env_var)
    db.commit()
    return None
