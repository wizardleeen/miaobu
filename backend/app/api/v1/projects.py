from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func as sa_func

from ...database import get_db
from ...models import User, Project, Deployment, DeploymentStatus, CustomDomain
from ...schemas import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectWithDeployments
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException, ConflictException
from ...config import get_settings
from ...services.esa import ESAService
from ...services.oss import OSSService

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


STALE_DEPLOYMENT_MINUTES = 20  # GHA timeout is 15 min


def _fail_stale_deployments(project_id: int, db: Session) -> None:
    """Mark deployments stuck in pre-deployed states as FAILED."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_DEPLOYMENT_MINUTES)
    stale = (
        db.query(Deployment)
        .filter(
            Deployment.project_id == project_id,
            Deployment.status.in_([
                DeploymentStatus.QUEUED,
                DeploymentStatus.CLONING,
                DeploymentStatus.BUILDING,
                DeploymentStatus.UPLOADING,
                DeploymentStatus.DEPLOYING,
            ]),
            Deployment.created_at < cutoff,
        )
        .all()
    )
    for d in stale:
        d.status = DeploymentStatus.FAILED
        d.error_message = "Build timed out — no status update received"
    if stale:
        db.commit()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new project."""
    # Check if project with same repo + root directory already exists for this user
    existing = db.query(Project).filter(
        Project.user_id == current_user.id,
        Project.github_repo_id == project_data.github_repo_id,
        Project.root_directory == (project_data.root_directory or "")
    ).first()

    if existing:
        raise ConflictException("Project with this repository and root directory already exists")

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
    """List all projects for the current user, ordered by most recent build activity."""
    latest_deploy = (
        db.query(sa_func.max(Deployment.created_at))
        .filter(Deployment.project_id == Project.id)
        .correlate(Project)
        .scalar_subquery()
    )
    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(latest_deploy.desc().nulls_last(), Project.created_at.desc())
        .all()
    )
    return projects


@router.get("/stats/dashboard")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard statistics for the current user."""
    user_project_ids = db.query(Project.id).filter(Project.user_id == current_user.id).subquery()

    # Active deployments: currently in-progress (queued, cloning, building, uploading, deploying)
    active_deployments = (
        db.query(sa_func.count(Deployment.id))
        .filter(
            Deployment.project_id.in_(user_project_ids),
            Deployment.status.in_([
                DeploymentStatus.QUEUED,
                DeploymentStatus.CLONING,
                DeploymentStatus.BUILDING,
                DeploymentStatus.UPLOADING,
                DeploymentStatus.DEPLOYING,
            ]),
        )
        .scalar()
    )

    # Builds this month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    builds_this_month = (
        db.query(sa_func.count(Deployment.id))
        .filter(
            Deployment.project_id.in_(user_project_ids),
            Deployment.created_at >= month_start,
        )
        .scalar()
    )

    return {
        "active_deployments": active_deployments or 0,
        "builds_this_month": builds_this_month or 0,
    }


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

    _fail_stale_deployments(project.id, db)
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

    _fail_stale_deployments(project.id, db)
    return project


logger = logging.getLogger(__name__)


def _refresh_edge_kv_on_spa_change(project: Project, db: Session) -> None:
    """Update Edge KV entries and purge CDN cache when is_spa changes."""
    settings = get_settings()
    esa_service = ESAService()
    subdomain = f"{project.slug}.{settings.cdn_base_domain}"

    # Find the latest deployed deployment for KV values
    latest = (
        db.query(Deployment)
        .filter(
            Deployment.project_id == project.id,
            Deployment.status == DeploymentStatus.DEPLOYED,
        )
        .order_by(Deployment.deployed_at.desc())
        .first()
    )
    if not latest:
        return

    # Collect all hostnames to update
    hostnames = [subdomain]
    custom_domains = (
        db.query(CustomDomain)
        .filter(
            CustomDomain.project_id == project.id,
            CustomDomain.is_verified == True,
        )
        .all()
    )
    for cd in custom_domains:
        hostnames.append(cd.domain)

    # Build KV value template
    def make_kv(hostname: str, deployment: Deployment) -> str:
        oss_path = f"projects/{project.slug}/{deployment.id}"
        return json.dumps({
            "type": "static",
            "oss_path": oss_path,
            "is_spa": project.is_spa,
            "project_slug": project.slug,
            "deployment_id": deployment.id,
            "commit_sha": deployment.commit_sha,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Update subdomain KV
    result = esa_service.put_edge_kv(subdomain, make_kv(subdomain, latest))
    if result["success"]:
        logger.info(f"Edge KV updated for {subdomain} (is_spa={project.is_spa})")
    else:
        logger.warning(f"Edge KV update failed for {subdomain}: {result.get('error')}")

    # Update custom domain KVs (each may have its own pinned deployment)
    for cd in custom_domains:
        dep = latest
        if cd.active_deployment_id and cd.active_deployment_id != latest.id:
            pinned = db.query(Deployment).filter(
                Deployment.id == cd.active_deployment_id,
                Deployment.status == DeploymentStatus.DEPLOYED,
            ).first()
            if pinned:
                dep = pinned
        result = esa_service.put_edge_kv(cd.domain, make_kv(cd.domain, dep))
        if result["success"]:
            logger.info(f"Edge KV updated for {cd.domain} (is_spa={project.is_spa})")
        else:
            logger.warning(f"Edge KV update failed for {cd.domain}: {result.get('error')}")

    # Purge CDN cache for all affected hostnames
    try:
        purge_result = esa_service.purge_host_cache(hostnames)
        if purge_result.get("success"):
            logger.info(f"CDN cache purged for {', '.join(hostnames)}")
        else:
            logger.warning(f"CDN cache purge failed: {purge_result.get('error')}")
    except Exception as e:
        logger.warning(f"CDN cache purge failed: {e}")


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
    is_spa_changed = "is_spa" in update_data and update_data["is_spa"] != project.is_spa
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    # When is_spa changes, update Edge KV entries and purge CDN cache
    if is_spa_changed and project.project_type != "python":
        _refresh_edge_kv_on_spa_change(project, db)

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

    settings = get_settings()
    esa_service = ESAService()

    # Clean up custom domain ESA resources (SaaS managers + Edge KV)
    custom_domains = (
        db.query(CustomDomain)
        .filter(
            CustomDomain.project_id == project.id,
            CustomDomain.is_verified == True,
        )
        .all()
    )
    for cd in custom_domains:
        try:
            if cd.esa_saas_id:
                esa_service.delete_saas_manager(cd.esa_saas_id)
            esa_service.delete_edge_kv(cd.domain)
        except Exception as e:
            logger.warning(f"Failed to clean up domain {cd.domain}: {e}")

    # Delete subdomain Edge KV
    try:
        esa_service.delete_edge_kv(f"{project.slug}.{settings.cdn_base_domain}")
    except Exception as e:
        logger.warning(f"Failed to delete subdomain Edge KV: {e}")

    # Delete all OSS files for the project
    try:
        oss_service = OSSService()
        oss_service.delete_directory(f"projects/{project.slug}/")
    except Exception as e:
        logger.warning(f"Failed to delete OSS files: {e}")

    # Delete FC packages from Qingdao bucket for Python/Node.js projects
    if project.project_type in ("python", "node"):
        try:
            from ...config import get_settings
            settings = get_settings()
            fc_oss_service = OSSService(
                bucket_name=settings.aliyun_fc_oss_bucket,
                endpoint=settings.aliyun_fc_oss_endpoint,
            )
            fc_oss_service.delete_directory(f"projects/{project.slug}/")
        except Exception as e:
            logger.warning(f"Failed to delete FC OSS files: {e}")

    # Clean up FC function for Python/Node.js projects
    if project.project_type in ("python", "node") and project.fc_function_name:
        try:
            from ...services.fc import FCService
            fc_service = FCService()
            fc_service.delete_function(project.fc_function_name)
        except Exception as e:
            logger.warning(f"Failed to delete FC function {project.fc_function_name}: {e}")

    db.delete(project)
    db.commit()

    return None
