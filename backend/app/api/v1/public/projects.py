"""Public API — Project endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from ....database import get_db
from ....models import User, Project
from ....core.security import get_current_user_flexible
from ....core.exceptions import NotFoundException, ForbiddenException
from .helpers import PaginationParams, paginated_response, single_response

router = APIRouter(tags=["Public API - Projects"])


def _project_dict(p: Project) -> dict:
    """Serialize a Project to a public API dict."""
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "project_type": p.project_type,
        "github_repo_name": p.github_repo_name,
        "github_repo_url": p.github_repo_url,
        "default_branch": p.default_branch,
        "root_directory": p.root_directory,
        "build_command": p.build_command,
        "install_command": p.install_command,
        "output_directory": p.output_directory,
        "is_spa": p.is_spa,
        "node_version": p.node_version,
        "python_version": p.python_version,
        "start_command": p.start_command,
        "manul_app_id": p.manul_app_id,
        "manul_app_name": p.manul_app_name,
        "default_domain": p.default_domain,
        "active_deployment_id": p.active_deployment_id,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _get_user_project(project_id: int, user: User, db: Session) -> Project:
    """Get a project and verify ownership."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != user.id:
        raise ForbiddenException("You don't have access to this project")
    return project


@router.get("/projects")
async def list_projects(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """List all projects for the authenticated user."""
    query = db.query(Project).filter(Project.user_id == current_user.id)
    total = query.count()
    projects = (
        query.order_by(Project.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.per_page)
        .all()
    )
    return paginated_response(
        [_project_dict(p) for p in projects],
        total,
        pagination.page,
        pagination.per_page,
    )


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Get a project by ID."""
    project = _get_user_project(project_id, current_user, db)
    return single_response(_project_dict(project))


@router.get("/projects/slug/{slug}")
async def get_project_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Get a project by slug."""
    project = db.query(Project).filter(Project.slug == slug).first()
    if not project:
        raise NotFoundException("Project not found")
    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")
    return single_response(_project_dict(project))


class ProjectUpdateBody(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    build_command: Optional[str] = Field(None, max_length=512)
    install_command: Optional[str] = Field(None, max_length=512)
    output_directory: Optional[str] = Field(None, max_length=255)
    root_directory: Optional[str] = Field(None, max_length=255)
    is_spa: Optional[bool] = None
    node_version: Optional[str] = Field(None, max_length=20)
    python_version: Optional[str] = Field(None, max_length=20)
    start_command: Optional[str] = Field(None, max_length=512)


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: int,
    body: ProjectUpdateBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Update a project's settings."""
    project = _get_user_project(project_id, current_user, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return single_response(_project_dict(project))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Delete a project and all associated resources."""
    project = _get_user_project(project_id, current_user, db)

    # Reuse the same cleanup logic from the internal endpoint
    from ....services.esa import ESAService
    from ....services.oss import OSSService
    from ....config import get_settings

    settings = get_settings()

    # Delete Manul app from the Manul server
    if project.project_type == "manul" and project.manul_app_id:
        try:
            from ....services.manul import ManulService
            ManulService().delete_app(project.manul_app_id)
        except Exception:
            pass

    # Best-effort cloud resource cleanup
    try:
        esa_service = ESAService()
        for cd in project.custom_domains:
            if cd.esa_saas_id:
                esa_service.delete_saas_manager(cd.esa_saas_id)
            esa_service.delete_edge_kv_mapping(cd.domain)
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
        esa_service.delete_edge_kv_mapping(subdomain)
    except Exception:
        pass

    try:
        oss_service = OSSService()
        oss_service.delete_directory(f"projects/{project.slug}/")
    except Exception:
        pass

    # Delete FC packages from Qingdao bucket for Manul projects
    if project.project_type == "manul":
        try:
            fc_oss = OSSService(
                bucket_name=settings.aliyun_fc_oss_bucket,
                endpoint=settings.aliyun_fc_oss_endpoint,
            )
            fc_oss.delete_directory(f"projects/{project.slug}/")
        except Exception:
            pass

    if project.project_type in ("python", "node"):
        from ....services.fc import FCService
        from ....services.alidns import AliDNSService
        fc_svc = FCService()
        dns_svc = AliDNSService()

        if project.fc_function_name:
            try:
                fc_svc.delete_function(project.fc_function_name)
            except Exception:
                pass

        # Clean up FC custom domain + DNS CNAME for production subdomain
        prod_subdomain = f"{project.slug}.{settings.cdn_base_domain}"
        try:
            fc_svc.delete_custom_domain(prod_subdomain)
        except Exception:
            pass
        try:
            dns_svc.delete_cname_record(prod_subdomain)
        except Exception:
            pass

        # Clean up staging FC resources if enabled
        if project.staging_enabled:
            staging_subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"
            if project.staging_fc_function_name:
                try:
                    fc_svc.delete_function(project.staging_fc_function_name)
                except Exception:
                    pass
            try:
                fc_svc.delete_custom_domain(staging_subdomain)
            except Exception:
                pass
            try:
                dns_svc.delete_cname_record(staging_subdomain)
            except Exception:
                pass

        try:
            fc_oss = OSSService(
                bucket_name=settings.aliyun_fc_oss_bucket,
                endpoint=settings.aliyun_fc_oss_endpoint,
            )
            fc_oss.delete_directory(f"projects/{project.slug}/")
        except Exception:
            pass

    db.delete(project)
    db.commit()
    return None
