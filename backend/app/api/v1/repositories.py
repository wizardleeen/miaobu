from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import httpx

from ...database import get_db
from ...models import User, Project
from ...services.github import GitHubService
from ...core.security import get_current_user
from ...core.exceptions import BadRequestException, ConflictException
from ...api.v1.projects import generate_slug
from ...config import get_settings


class ImportRepositoryRequest(BaseModel):
    branch: Optional[str] = None
    root_directory: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = None

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.get("")
async def list_repositories(
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List user's GitHub repositories.

    Supports pagination and optional search.
    """
    try:
        if search:
            # Search repositories
            result = await GitHubService.search_repositories(
                current_user.github_access_token,
                search,
                page,
                per_page
            )
            repositories = result.get("items", [])
            total_count = result.get("total_count", 0)
        else:
            # List all repositories
            repositories = await GitHubService.list_repositories(
                current_user.github_access_token,
                page,
                per_page
            )
            total_count = len(repositories)

        # Get list of already imported repo IDs
        imported_repo_ids = db.query(Project.github_repo_id).filter(
            Project.user_id == current_user.id
        ).all()
        imported_ids = {repo_id[0] for repo_id in imported_repo_ids}

        # Format response
        formatted_repos = []
        for repo in repositories:
            formatted_repos.append({
                "id": repo["id"],
                "name": repo["name"],
                "full_name": repo["full_name"],
                "html_url": repo["html_url"],
                "description": repo.get("description"),
                "language": repo.get("language"),
                "default_branch": repo.get("default_branch", "main"),
                "private": repo.get("private", False),
                "updated_at": repo.get("updated_at"),
                "is_imported": repo["id"] in imported_ids,
            })

        return {
            "repositories": formatted_repos,
            "total": total_count,
            "page": page,
            "per_page": per_page,
        }

    except Exception as e:
        raise BadRequestException(f"Failed to fetch repositories: {str(e)}")


@router.get("/{owner}/{repo}/analyze")
async def analyze_repository(
    owner: str,
    repo: str,
    branch: Optional[str] = None,
    root_directory: Optional[str] = Query(None, description="Subdirectory path for monorepo support (e.g., 'frontend')"),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze a GitHub repository and detect build configuration.

    Supports monorepo projects via the root_directory parameter.

    Returns repository info with auto-detected build settings.
    """
    try:
        analysis = await GitHubService.analyze_repository(
            current_user.github_access_token,
            owner,
            repo,
            branch,
            root_directory or ""
        )
        return analysis

    except Exception as e:
        raise BadRequestException(f"Failed to analyze repository: {str(e)}")


@router.post("/{owner}/{repo}/import")
async def import_repository(
    owner: str,
    repo: str,
    body: ImportRepositoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import a GitHub repository as a new project.

    Automatically detects build configuration and creates the project.
    Optionally accepts custom configuration to override auto-detected settings.
    Supports monorepo projects via the root_directory parameter.
    """
    settings = get_settings()
    try:
        # Analyze repository
        branch = body.branch
        root_directory = body.root_directory
        custom_config = body.custom_config

        analysis = await GitHubService.analyze_repository(
            current_user.github_access_token,
            owner,
            repo,
            branch,
            root_directory or ""
        )

        repo_info = analysis["repository"]
        build_config = analysis["build_config"]
        detected_root_dir = analysis.get("root_directory", "")
        detected_project_type = analysis.get("project_type", "static")

        # Check if already imported (same repo + same root directory = duplicate)
        # Use custom_config root_directory if provided, else detected, else input param
        check_root_dir = ""
        if custom_config and custom_config.get("root_directory"):
            check_root_dir = custom_config["root_directory"]
        elif detected_root_dir:
            check_root_dir = detected_root_dir
        elif root_directory:
            check_root_dir = root_directory

        existing = db.query(Project).filter(
            Project.user_id == current_user.id,
            Project.github_repo_id == repo_info["id"],
            Project.root_directory == check_root_dir
        ).first()

        if existing:
            label = f"{repo_info['full_name']}/{check_root_dir}" if check_root_dir else repo_info['full_name']
            raise ConflictException(f"Repository {label} is already imported")

        # Use custom config if provided, otherwise use detected config
        if custom_config:
            project_name = custom_config.get("name", repo_info["name"])
            root_dir = custom_config.get("root_directory", detected_root_dir)
            project_type_str = custom_config.get("project_type", detected_project_type)
        else:
            project_name = repo_info["name"]
            root_dir = detected_root_dir
            project_type_str = detected_project_type

        project_type = "python" if project_type_str == "python" else "static"

        # Generate unique slug
        slug = generate_slug(project_name, current_user.id, db)

        # Build project kwargs
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
            # Python-specific fields
            if custom_config:
                project_kwargs["python_version"] = custom_config.get("python_version", build_config.get("python_version", "3.11"))
                project_kwargs["start_command"] = custom_config.get("start_command", build_config.get("start_command", ""))
                project_kwargs["python_framework"] = custom_config.get("python_framework", build_config.get("python_framework"))
            else:
                project_kwargs["python_version"] = build_config.get("python_version", "3.11")
                project_kwargs["start_command"] = build_config.get("start_command", "")
                project_kwargs["python_framework"] = build_config.get("python_framework")
        else:
            # Static/Node.js fields
            if custom_config:
                project_kwargs["build_command"] = custom_config.get("build_command", build_config.get("build_command", "npm run build"))
                project_kwargs["install_command"] = custom_config.get("install_command", build_config.get("install_command", "npm install"))
                project_kwargs["output_directory"] = custom_config.get("output_directory", build_config.get("output_directory", "dist"))
                project_kwargs["node_version"] = custom_config.get("node_version", build_config.get("node_version", "18"))
                project_kwargs["is_spa"] = custom_config.get("is_spa", build_config.get("is_spa", True))
            else:
                project_kwargs["build_command"] = build_config.get("build_command", "npm run build")
                project_kwargs["install_command"] = build_config.get("install_command", "npm install")
                project_kwargs["output_directory"] = build_config.get("output_directory", "dist")
                project_kwargs["node_version"] = build_config.get("node_version", "18")
                project_kwargs["is_spa"] = build_config.get("is_spa", True)

        # Create project
        project = Project(**project_kwargs)

        db.add(project)
        db.commit()
        db.refresh(project)

        # Note: CDN subdomains work automatically via wildcard domain (*.metavm.tech)
        # No per-project CDN configuration needed!

        # Automatically create GitHub webhook for this project
        webhook_created = False
        webhook_error = None
        try:
            import secrets

            # Generate webhook secret
            webhook_secret = secrets.token_urlsafe(32)

            # Construct webhook URL
            webhook_url = f"{settings.backend_url}/api/v1/webhooks/github/{project.id}"

            # Create webhook on GitHub
            webhook = await GitHubService.create_webhook(
                current_user.github_access_token,
                owner,
                repo,
                webhook_url,
                webhook_secret
            )

            # Save webhook info to project
            project.webhook_id = webhook["id"]
            project.webhook_secret = webhook_secret
            db.commit()

            webhook_created = True

        except Exception as e:
            # Don't fail the import if webhook creation fails
            webhook_error = str(e)
            print(f"Warning: Failed to create webhook for project {project.id}: {e}")

        # Automatically trigger first deployment
        deployment_triggered = False
        deployment_id = None
        deployment_error = None
        try:
            from ...models import Deployment, DeploymentStatus
            from ...services.github_actions import trigger_build

            # Get latest commit info from GitHub
            try:
                branch_url = f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/branches/{repo_info['default_branch']}"
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        branch_url,
                        headers={
                            "Authorization": f"Bearer {current_user.github_access_token}",
                            "Accept": "application/vnd.github.v3+json",
                        }
                    )
                    response.raise_for_status()
                    branch_data = response.json()

                    latest_commit = branch_data['commit']
                    commit_sha = latest_commit['sha']
                    commit_message = latest_commit['commit']['message']
                    commit_author = latest_commit['commit']['author']['name']

            except Exception as e:
                # Fallback to manual deployment
                commit_sha = "initial"
                commit_message = f"Initial deployment after import"
                commit_author = current_user.github_username

            # Create deployment record
            deployment = Deployment(
                project_id=project.id,
                commit_sha=commit_sha,
                commit_message=commit_message,
                commit_author=commit_author,
                branch=repo_info['default_branch'],
                status=DeploymentStatus.QUEUED
            )

            db.add(deployment)
            db.commit()
            db.refresh(deployment)

            # Dispatch build via GitHub Actions
            result = await trigger_build(project, deployment)
            if not result["success"]:
                raise Exception(result["error"])

            deployment_triggered = True
            deployment_id = deployment.id

        except Exception as e:
            # Don't fail the import if deployment fails
            deployment_error = str(e)
            print(f"Warning: Failed to trigger initial deployment for project {project.id}: {e}")

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "slug": project.slug,
                "project_type": project.project_type or "static",
                "github_repo_name": project.github_repo_name,
                "default_domain": project.default_domain,
                "root_directory": project.root_directory,
                "build_command": project.build_command,
                "install_command": project.install_command,
                "output_directory": project.output_directory,
                "node_version": project.node_version,
                "python_version": project.python_version,
                "start_command": project.start_command,
                "python_framework": project.python_framework,
                "webhook_id": project.webhook_id,
                "webhook_configured": webhook_created,
                "created_at": project.created_at,
            },
            "detected_framework": build_config["framework"],
            "detection_confidence": build_config["confidence"],
            "project_type": project_type_str,
            "note": build_config.get("note"),
            "webhook_status": {
                "created": webhook_created,
                "error": webhook_error
            },
            "deployment_status": {
                "triggered": deployment_triggered,
                "deployment_id": deployment_id,
                "error": deployment_error,
                "message": "Initial deployment queued" if deployment_triggered else "Deployment not triggered"
            }
        }

    except ConflictException:
        raise
    except Exception as e:
        raise BadRequestException(f"Failed to import repository: {str(e)}")
