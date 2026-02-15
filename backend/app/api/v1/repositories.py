from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ...database import get_db
from ...models import User, Project
from ...services.github import GitHubService
from ...core.security import get_current_user
from ...core.exceptions import BadRequestException, ConflictException
from ...api.v1.projects import generate_slug

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
    current_user: User = Depends(get_current_user)
):
    """
    Analyze a GitHub repository and detect build configuration.

    Returns repository info with auto-detected build settings.
    """
    try:
        analysis = await GitHubService.analyze_repository(
            current_user.github_access_token,
            owner,
            repo,
            branch
        )
        return analysis

    except Exception as e:
        raise BadRequestException(f"Failed to analyze repository: {str(e)}")


@router.post("/{owner}/{repo}/import")
async def import_repository(
    owner: str,
    repo: str,
    branch: Optional[str] = None,
    custom_config: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import a GitHub repository as a new project.

    Automatically detects build configuration and creates the project.
    Optionally accepts custom configuration to override auto-detected settings.
    """
    try:
        # Analyze repository
        analysis = await GitHubService.analyze_repository(
            current_user.github_access_token,
            owner,
            repo,
            branch
        )

        repo_info = analysis["repository"]
        build_config = analysis["build_config"]

        # Check if already imported
        existing = db.query(Project).filter(
            Project.user_id == current_user.id,
            Project.github_repo_id == repo_info["id"]
        ).first()

        if existing:
            raise ConflictException(f"Repository {repo_info['full_name']} is already imported")

        # Use custom config if provided, otherwise use detected config
        if custom_config:
            build_command = custom_config.get("build_command", build_config["build_command"])
            install_command = custom_config.get("install_command", build_config["install_command"])
            output_directory = custom_config.get("output_directory", build_config["output_directory"])
            node_version = custom_config.get("node_version", build_config["node_version"])
            project_name = custom_config.get("name", repo_info["name"])
        else:
            build_command = build_config["build_command"]
            install_command = build_config["install_command"]
            output_directory = build_config["output_directory"]
            node_version = build_config["node_version"]
            project_name = repo_info["name"]

        # Generate unique slug
        slug = generate_slug(project_name, current_user.id, db)

        # Create project
        project = Project(
            user_id=current_user.id,
            github_repo_id=repo_info["id"],
            github_repo_name=repo_info["full_name"],
            github_repo_url=repo_info["html_url"],
            default_branch=repo_info["default_branch"],
            name=project_name,
            slug=slug,
            build_command=build_command,
            install_command=install_command,
            output_directory=output_directory,
            node_version=node_version,
            oss_path=f"{current_user.id}/{slug}/",
            default_domain=f"{slug}.miaobu.app"
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        # Automatically create GitHub webhook for this project
        webhook_created = False
        webhook_error = None
        try:
            from ...config import get_settings
            import secrets

            settings = get_settings()

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

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "slug": project.slug,
                "github_repo_name": project.github_repo_name,
                "default_domain": project.default_domain,
                "build_command": project.build_command,
                "install_command": project.install_command,
                "output_directory": project.output_directory,
                "node_version": project.node_version,
                "webhook_id": project.webhook_id,
                "webhook_configured": webhook_created,
                "created_at": project.created_at,
            },
            "detected_framework": build_config["framework"],
            "detection_confidence": build_config["confidence"],
            "note": build_config.get("note"),
            "webhook_status": {
                "created": webhook_created,
                "error": webhook_error
            }
        }

    except ConflictException:
        raise
    except Exception as e:
        raise BadRequestException(f"Failed to import repository: {str(e)}")
