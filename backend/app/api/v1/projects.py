from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import re

from ...database import get_db
from ...models import User, Project
from ...schemas import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectWithDeployments
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, ConflictException

router = APIRouter(prefix="/projects", tags=["Projects"])


def generate_slug(name: str, user_id: int, db: Session) -> str:
    """Generate a unique slug for a project."""
    # Convert to lowercase, replace spaces with hyphens, remove special chars
    base_slug = re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))
    slug = base_slug

    # Ensure uniqueness
    counter = 1
    while db.query(Project).filter(Project.slug == slug).first():
        slug = f"{base_slug}-{counter}"
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
        oss_path=f"{current_user.id}/{slug}/",
        default_domain=f"{slug}.miaobu.app"
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

    db.delete(project)
    db.commit()

    return None
