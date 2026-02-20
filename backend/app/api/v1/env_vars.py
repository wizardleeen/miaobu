from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List

from ...database import get_db
from ...models import User, Project, EnvironmentVariable
from ...schemas import (
    EnvironmentVariableCreate,
    EnvironmentVariableUpdate,
    EnvironmentVariableResponse,
)
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, ConflictException

router = APIRouter(prefix="/projects/{project_id}/env", tags=["Environment Variables"])

MASK = "••••••••"


def _get_project_or_403(project_id: int, user: User, db: Session) -> Project:
    """Get project and verify ownership."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


@router.get("", response_model=List[EnvironmentVariableResponse])
async def list_env_vars(
    project_id: int,
    environment: str = "production",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List environment variables for a project. Secret values are masked."""
    _get_project_or_403(project_id, current_user, db)

    env_vars = db.query(EnvironmentVariable).filter(
        EnvironmentVariable.project_id == project_id,
        EnvironmentVariable.environment == environment,
    ).order_by(EnvironmentVariable.key).all()

    # Mask secret values in the response
    results = []
    for ev in env_vars:
        value = MASK if ev.is_secret else ev.value
        # Decrypt non-secret values for display
        if not ev.is_secret:
            try:
                from ...services.encryption import decrypt_value
                value = decrypt_value(ev.value)
            except Exception:
                value = ev.value

        results.append(EnvironmentVariableResponse(
            id=ev.id,
            project_id=ev.project_id,
            key=ev.key,
            value=value,
            is_secret=ev.is_secret,
            environment=ev.environment,
            created_at=ev.created_at,
            updated_at=ev.updated_at,
        ))

    return results


@router.post("", response_model=EnvironmentVariableResponse, status_code=status.HTTP_201_CREATED)
async def create_env_var(
    project_id: int,
    data: EnvironmentVariableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new environment variable."""
    _get_project_or_403(project_id, current_user, db)

    # Check for duplicate key within the same environment
    env = data.environment if hasattr(data, 'environment') else "production"
    existing = db.query(EnvironmentVariable).filter(
        EnvironmentVariable.project_id == project_id,
        EnvironmentVariable.key == data.key,
        EnvironmentVariable.environment == env,
    ).first()

    if existing:
        raise ConflictException(f"Environment variable '{data.key}' already exists")

    # Encrypt value
    from ...services.encryption import encrypt_value
    encrypted_value = encrypt_value(data.value)

    env_var = EnvironmentVariable(
        project_id=project_id,
        key=data.key,
        value=encrypted_value,
        is_secret=data.is_secret,
        environment=env,
    )

    db.add(env_var)
    db.commit()
    db.refresh(env_var)

    return EnvironmentVariableResponse(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value=MASK if env_var.is_secret else data.value,
        is_secret=env_var.is_secret,
        environment=env_var.environment,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


@router.patch("/{var_id}", response_model=EnvironmentVariableResponse)
async def update_env_var(
    project_id: int,
    var_id: int,
    data: EnvironmentVariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an environment variable."""
    _get_project_or_403(project_id, current_user, db)

    env_var = db.query(EnvironmentVariable).filter(
        EnvironmentVariable.id == var_id,
        EnvironmentVariable.project_id == project_id,
    ).first()

    if not env_var:
        raise NotFoundException("Environment variable not found")

    if data.key is not None:
        # Check for duplicate key (if changing key)
        if data.key != env_var.key:
            existing = db.query(EnvironmentVariable).filter(
                EnvironmentVariable.project_id == project_id,
                EnvironmentVariable.key == data.key,
                EnvironmentVariable.id != var_id,
            ).first()
            if existing:
                raise ConflictException(f"Environment variable '{data.key}' already exists")
        env_var.key = data.key

    display_value = None
    if data.value is not None:
        from ...services.encryption import encrypt_value
        env_var.value = encrypt_value(data.value)
        display_value = data.value

    if data.is_secret is not None:
        env_var.is_secret = data.is_secret

    db.commit()
    db.refresh(env_var)

    # Determine display value
    if env_var.is_secret:
        value = MASK
    elif display_value is not None:
        value = display_value
    else:
        try:
            from ...services.encryption import decrypt_value
            value = decrypt_value(env_var.value)
        except Exception:
            value = env_var.value

    return EnvironmentVariableResponse(
        id=env_var.id,
        project_id=env_var.project_id,
        key=env_var.key,
        value=value,
        is_secret=env_var.is_secret,
        environment=env_var.environment,
        created_at=env_var.created_at,
        updated_at=env_var.updated_at,
    )


@router.delete("/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_env_var(
    project_id: int,
    var_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an environment variable."""
    _get_project_or_403(project_id, current_user, db)

    env_var = db.query(EnvironmentVariable).filter(
        EnvironmentVariable.id == var_id,
        EnvironmentVariable.project_id == project_id,
    ).first()

    if not env_var:
        raise NotFoundException("Environment variable not found")

    db.delete(env_var)
    db.commit()

    return None
