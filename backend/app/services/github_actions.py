"""
GitHub Actions dispatch service.

Triggers repository_dispatch events on the miaobu repo to start builds
via GitHub Actions instead of the local Celery worker.
"""
import json
import httpx
from typing import Dict, Any

from ..config import get_settings
from ..models import Project, Deployment


# The miaobu infrastructure repo that hosts the build workflow
MIAOBU_REPO = "wizardleeen/miaobu"


async def trigger_build(project: Project, deployment: Deployment) -> Dict[str, Any]:
    """
    Trigger a GitHub Actions build via repository_dispatch.

    Args:
        project: The project being deployed
        deployment: The deployment record (must already be committed to DB)

    Returns:
        {"success": True} or {"success": False, "error": "..."}
    """
    settings = get_settings()

    if not settings.github_pat:
        return {"success": False, "error": "github_pat not configured"}

    # GitHub limits client_payload to 10 properties.
    # Pack build config into a single JSON string.
    build_config = json.dumps({
        "install_command": project.install_command or "npm install",
        "build_command": project.build_command if project.build_command else ("" if project.project_type == "node" else "npm run build"),
        "output_directory": project.output_directory or "dist",
        "node_version": project.node_version or "18",
        "root_directory": project.root_directory or "",
        "is_spa": project.is_spa,
        "python_version": project.python_version or "3.10",
        "start_command": project.start_command or "",
    })

    payload = {
        "event_type": "miaobu-build",
        "client_payload": {
            "deployment_id": deployment.id,
            "project_type": project.project_type or "static",
            "repo_name": project.github_repo_name,
            "branch": deployment.branch,
            "commit_sha": deployment.commit_sha,
            "project_slug": project.slug,
            "build_config": build_config,
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/repos/{MIAOBU_REPO}/dispatches",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.github_pat}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30,
            )

        # repository_dispatch returns 204 No Content on success
        if response.status_code == 204:
            return {"success": True}
        else:
            return {
                "success": False,
                "error": f"GitHub API returned {response.status_code}: {response.text}",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
