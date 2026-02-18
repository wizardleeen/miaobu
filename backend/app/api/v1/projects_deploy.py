from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
import httpx

from ...database import get_db
from ...models import User, Project, Deployment, DeploymentStatus
from ...core.security import get_current_user
from ...core.exceptions import NotFoundException, ForbiddenException
from ...services.github import GitHubService

router = APIRouter(tags=["Projects"])


@router.post("/projects/{project_id}/deploy", status_code=status.HTTP_201_CREATED)
async def trigger_deployment(
    project_id: int,
    branch: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a new deployment for a project.

    Fetches latest commit from GitHub and queues build job.
    """
    # Get project
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise NotFoundException("Project not found")

    if project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this project")

    # Use specified branch or default branch
    deploy_branch = branch or project.default_branch

    # Get latest commit info from GitHub
    try:
        owner, repo = project.github_repo_name.split('/')
        repo_info = await GitHubService.get_repository(
            current_user.github_access_token,
            owner,
            repo
        )

        # Get branch info to get latest commit
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/branches/{deploy_branch}",
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
        # Fallback to manual deployment without commit info
        commit_sha = "manual"
        commit_message = f"Manual deployment triggered"
        commit_author = current_user.github_username

    # Create deployment record
    deployment = Deployment(
        project_id=project.id,
        commit_sha=commit_sha,
        commit_message=commit_message,
        commit_author=commit_author,
        branch=deploy_branch,
        status=DeploymentStatus.QUEUED
    )

    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Dispatch build via GitHub Actions
    try:
        from ...services.github_actions import trigger_build

        result = await trigger_build(project, deployment)
        if not result["success"]:
            raise Exception(result["error"])
    except Exception as e:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"Failed to dispatch build: {str(e)}"
        db.commit()
        raise

    return {
        "deployment_id": deployment.id,
        "status": deployment.status,
        "commit_sha": commit_sha,
        "commit_message": commit_message,
        "branch": deploy_branch,
    }


@router.post("/deployments/{deployment_id}/cancel")
async def cancel_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a running deployment."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()

    if not deployment:
        raise NotFoundException("Deployment not found")

    if deployment.project.user_id != current_user.id:
        raise ForbiddenException("You don't have access to this deployment")

    # Can only cancel queued or in-progress deployments
    if deployment.status in [DeploymentStatus.DEPLOYED, DeploymentStatus.FAILED, DeploymentStatus.CANCELLED]:
        raise Exception(f"Cannot cancel deployment with status {deployment.status}")

    # Update status (GHA workflows will check deployment status and stop if cancelled)
    deployment.status = DeploymentStatus.CANCELLED
    db.commit()

    return {"success": True, "deployment_id": deployment_id}
