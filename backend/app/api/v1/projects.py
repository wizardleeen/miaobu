from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import re

from ...database import get_db
from ...models import User, Project
from ...schemas import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectWithDeployments
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, ConflictException
from ...config import get_settings

router = APIRouter(prefix="/projects", tags=["Projects"])


def generate_slug(name: str, user_id: int, db: Session) -> str:
    """
    Generate a globally unique slug for a project.

    Handles collisions by adding numeric suffix: app, app1, app2, etc.
    The slug determines:
    - OSS path: /projects/{slug}/
    - Subdomain: {slug}.metavm.tech
    """
    # Convert to lowercase, replace spaces/dots with hyphens, remove special chars
    base_slug = re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-').replace('.', '-'))

    # Remove leading/trailing hyphens
    base_slug = base_slug.strip('-')

    # Limit length for subdomain (max 63 chars for DNS)
    base_slug = base_slug[:50]

    # Start without suffix
    slug = base_slug

    # Check global uniqueness across ALL projects (not just this user)
    counter = 1
    while db.query(Project).filter(Project.slug == slug).first():
        slug = f"{base_slug}{counter}"  # app, app1, app2 (no hyphen for cleaner subdomain)
        counter += 1

    return slug


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new project."""
    # Check if project with same repo already exists for this user
    existing = db.query(Project).filter(
        Project.user_id == current_user.id,
        Project.github_repo_id == project_data.github_repo_id
    ).first()

    if existing:
        raise ConflictException("Project with this repository already exists")

    # Generate unique slug
    slug = generate_slug(project_data.name, current_user.id, db)

    # Get settings for CDN domain
    settings = get_settings()

    # Create project
    project = Project(
        user_id=current_user.id,
        github_repo_id=project_data.github_repo_id,
        github_repo_name=project_data.github_repo_name,
        github_repo_url=project_data.github_repo_url,
        default_branch=project_data.default_branch,
        name=project_data.name,
        slug=slug,
        build_command=project_data.build_command,
        install_command=project_data.install_command,
        output_directory=project_data.output_directory,
        node_version=project_data.node_version,
        oss_path=f"projects/{slug}/",  # NEW: Simplified path structure
        default_domain=f"{slug}.{settings.cdn_base_domain}"  # e.g., app.metavm.tech
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all projects for the current user."""
    projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    return projects


@router.get("/{project_id}", response_model=ProjectWithDeployments)
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific project with its deployments."""
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    return project


@router.get("/slug/{slug}", response_model=ProjectWithDeployments)
async def get_project_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a project by slug."""
    project = db.query(Project).filter(
        Project.slug == slug,
        Project.user_id == current_user.id
    ).first()

    if not project:
        raise NotFoundException("Project not found")

    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a project's configuration."""
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    # Update fields if provided
    update_data = project_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a project."""
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    # TODO: Delete webhook from GitHub
    # TODO: Clean up OSS files

    # Clean up FC function for Python projects
    if project.project_type == "python" and project.fc_function_name:
        try:
            from ...services.fc import FCService
            fc_service = FCService()
            fc_service.delete_function(project.fc_function_name)
        except Exception as e:
            print(f"Warning: Failed to delete FC function {project.fc_function_name}: {e}")

    db.delete(project)
    db.commit()

    return None
