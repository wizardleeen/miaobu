"""Public API — Project endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from ....database import get_db
from ....models import User, Project
from ....core.security import get_current_user_flexible
from ....core.exceptions import (
    BadRequestException, ConflictException, NotFoundException, ForbiddenException,
)
from .helpers import PaginationParams, paginated_response, single_response

logger = logging.getLogger(__name__)

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


class EnvVarInput(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str
    is_secret: bool = False


class CreateProjectBody(BaseModel):
    repo: str = Field(..., description="GitHub repo in 'owner/repo' format")
    branch: Optional[str] = None
    root_directory: Optional[str] = None
    project_type: Optional[str] = Field(None, pattern=r"^(static|node|python)$")
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    build_command: Optional[str] = Field(None, max_length=512)
    install_command: Optional[str] = Field(None, max_length=512)
    output_directory: Optional[str] = Field(None, max_length=255)
    node_version: Optional[str] = Field(None, max_length=20)
    is_spa: Optional[bool] = None
    python_version: Optional[str] = Field(None, max_length=20)
    start_command: Optional[str] = Field(None, max_length=512)
    python_framework: Optional[str] = Field(None, max_length=50)
    environment_variables: Optional[List[EnvVarInput]] = None


@router.post("/projects", status_code=201)
async def create_project(
    body: CreateProjectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Create a project from a GitHub repository.

    Only ``repo`` is required. All other fields are auto-detected from the
    repository if omitted.
    """
    from ....services.github import GitHubService
    from ....services.encryption import encrypt_value
    from ....services.github_actions import trigger_build
    from ....api.v1.projects import generate_slug
    from ....config import get_settings
    import httpx
    import secrets

    settings = get_settings()

    if not current_user.github_access_token:
        raise BadRequestException("GitHub account not connected")

    # Parse owner/repo
    parts = body.repo.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise BadRequestException("repo must be in 'owner/repo' format")
    owner, repo = parts

    # Analyze repository
    try:
        analysis = await GitHubService.analyze_repository(
            current_user.github_access_token,
            owner,
            repo,
            body.branch,
            body.root_directory or "",
        )
    except Exception as e:
        raise BadRequestException(f"Failed to analyze repository: {e}")

    repo_info = analysis["repository"]
    build_config = analysis["build_config"]
    detected_root_dir = analysis.get("root_directory", "")
    detected_project_type = analysis.get("project_type", "static")

    # Determine root directory
    root_dir = body.root_directory if body.root_directory is not None else detected_root_dir

    # Check for duplicate
    existing = db.query(Project).filter(
        Project.user_id == current_user.id,
        Project.github_repo_id == repo_info["id"],
        Project.root_directory == root_dir,
    ).first()
    if existing:
        label = f"{repo_info['full_name']}/{root_dir}" if root_dir else repo_info["full_name"]
        raise ConflictException(f"Repository {label} is already imported")

    # Determine project config — use body values if provided, else detected, else defaults
    project_name = body.name if body.name is not None else repo_info["name"]
    project_type = body.project_type if body.project_type is not None else detected_project_type

    slug = generate_slug(project_name, current_user.id, db)

    project_kwargs = dict(
        user_id=current_user.id,
        github_repo_id=repo_info["id"],
        github_repo_name=repo_info["full_name"],
        github_repo_url=repo_info["html_url"],
        default_branch=repo_info["default_branch"],
        name=project_name,
        slug=slug,
        root_directory=root_dir,
        project_type=project_type,
        oss_path=f"projects/{slug}/",
        default_domain=f"{slug}.{settings.cdn_base_domain}",
    )

    if project_type == "python":
        project_kwargs["python_version"] = (
            body.python_version if body.python_version is not None
            else build_config.get("python_version", "3.11")
        )
        project_kwargs["start_command"] = (
            body.start_command if body.start_command is not None
            else build_config.get("start_command", "")
        )
        project_kwargs["python_framework"] = (
            body.python_framework if body.python_framework is not None
            else build_config.get("python_framework")
        )
    elif project_type == "node":
        project_kwargs["start_command"] = (
            body.start_command if body.start_command is not None
            else build_config.get("start_command", "npm start")
        )
        project_kwargs["install_command"] = (
            body.install_command if body.install_command is not None
            else build_config.get("install_command", "npm install")
        )
        project_kwargs["build_command"] = (
            body.build_command if body.build_command is not None
            else build_config.get("build_command", "")
        )
        project_kwargs["node_version"] = (
            body.node_version if body.node_version is not None
            else build_config.get("node_version", "18")
        )
    else:
        # static
        project_kwargs["build_command"] = (
            body.build_command if body.build_command is not None
            else build_config.get("build_command", "npm run build")
        )
        project_kwargs["install_command"] = (
            body.install_command if body.install_command is not None
            else build_config.get("install_command", "npm install")
        )
        project_kwargs["output_directory"] = (
            body.output_directory if body.output_directory is not None
            else build_config.get("output_directory", "dist")
        )
        project_kwargs["node_version"] = (
            body.node_version if body.node_version is not None
            else build_config.get("node_version", "18")
        )
        project_kwargs["is_spa"] = (
            body.is_spa if body.is_spa is not None
            else build_config.get("is_spa", True)
        )

    project = Project(**project_kwargs)
    db.add(project)
    db.commit()
    db.refresh(project)

    # Setup ESA static subdomain (best-effort)
    if project_type == "static":
        try:
            from ....services.esa import ESAService
            esa_service = ESAService()
            subdomain = f"{slug}.{settings.cdn_base_domain}"
            result = esa_service.setup_static_subdomain(subdomain)
            if not result.get("success"):
                logger.warning(
                    f"Static subdomain setup failed for {subdomain}: "
                    f"{result.get('error') or result.get('errors')}"
                )
        except Exception as e:
            logger.warning(f"Static subdomain setup failed for {slug}: {e}")

    # Save environment variables
    env_vars_saved = False
    if body.environment_variables:
        try:
            from ....models import EnvironmentVariable

            for env_input in body.environment_variables:
                env_var = EnvironmentVariable(
                    project_id=project.id,
                    key=env_input.key,
                    value=encrypt_value(env_input.value),
                    is_secret=env_input.is_secret,
                )
                db.add(env_var)
            db.commit()
            env_vars_saved = True
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to save environment variables for project {project.id}: {e}")

    # Create GitHub webhook (non-fatal)
    webhook_created = False
    try:
        webhook_secret = secrets.token_urlsafe(32)
        webhook_url = f"{settings.backend_url}/api/v1/webhooks/github/{project.id}"
        webhook = await GitHubService.create_webhook(
            current_user.github_access_token,
            owner,
            repo,
            webhook_url,
            webhook_secret,
        )
        project.webhook_id = webhook["id"]
        project.webhook_secret = webhook_secret
        db.commit()
        webhook_created = True
    except Exception as e:
        logger.warning(f"Failed to create webhook for project {project.id}: {e}")

    # Trigger initial deployment (non-fatal)
    deployment_info = None
    try:
        from ....models import Deployment, DeploymentStatus

        # Get latest commit
        try:
            branch_url = (
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}"
                f"/branches/{repo_info['default_branch']}"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    branch_url,
                    headers={
                        "Authorization": f"Bearer {current_user.github_access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                resp.raise_for_status()
                branch_data = resp.json()
                commit_sha = branch_data["commit"]["sha"]
                commit_message = branch_data["commit"]["commit"]["message"]
                commit_author = branch_data["commit"]["commit"]["author"]["name"]
        except Exception:
            commit_sha = "initial"
            commit_message = "Initial deployment after import"
            commit_author = current_user.github_username

        deployment = Deployment(
            project_id=project.id,
            commit_sha=commit_sha,
            commit_message=commit_message,
            commit_author=commit_author,
            branch=repo_info["default_branch"],
            status=DeploymentStatus.QUEUED,
        )
        db.add(deployment)
        db.commit()
        db.refresh(deployment)

        result = await trigger_build(project, deployment)
        if not result["success"]:
            raise Exception(result["error"])

        deployment_info = {"id": deployment.id, "status": "queued"}
    except Exception as e:
        logger.warning(f"Failed to trigger initial deployment for project {project.id}: {e}")

    data = _project_dict(project)
    data["detected_framework"] = build_config.get("framework")
    data["detection_confidence"] = build_config.get("confidence")
    data["webhook_created"] = webhook_created
    data["env_vars_saved"] = env_vars_saved if body.environment_variables else None
    data["deployment"] = deployment_info
    return single_response(data)


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

    # Null out deployment FKs to break circular reference before cascade delete
    project.active_deployment_id = None
    project.staging_deployment_id = None
    db.flush()

    db.delete(project)
    db.commit()
    return None
