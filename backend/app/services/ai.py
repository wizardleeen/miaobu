"""
AI service for conversational project creation and modification.

Orchestrates a Claude tool-use loop: user message -> Claude -> tool calls -> results -> repeat.
Streams the entire interaction via SSE to the frontend.
"""
import asyncio
import json
import secrets
import traceback
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any, List, Optional

import anthropic
import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    User, Project, Deployment, DeploymentStatus,
    ChatSession, ChatMessage,
)
from .github import GitHubService
from .github_actions import trigger_build

settings = get_settings()

# --------------------------------------------------------------------------- #
# System prompt
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """You are Miaobu AI, an intelligent assistant integrated into the Miaobu deployment platform. You help users create new web projects and modify existing ones.

## Capabilities
You can:
- Create new GitHub repositories and scaffold complete web projects (React, Vue, Next.js, FastAPI, Flask, Express, etc.)
- Read and modify files in existing project repositories
- Create Miaobu projects from repositories and trigger deployments
- Update project settings (project type, build commands, etc.)
- List and inspect the user's existing projects
- Monitor deployments, read build logs, and automatically diagnose and fix build failures

## Guidelines
1. Detect the user's language from their messages and respond in the same language (default: Chinese).
2. Generate clean, production-ready code with all necessary config files (package.json, tsconfig, vite config, etc.).
3. For new projects: create repo -> write all files -> create Miaobu project -> trigger deployment.
4. For modifications: read the relevant files first -> commit changes -> trigger deployment.
5. Always explain what you're doing at each step.
6. When creating a project, pick sensible defaults for build config based on the framework.
7. Keep file contents complete — never use placeholder comments like "// rest of code here".
8. Repository names should be lowercase with hyphens, no special characters.

## Project Type Selection
- `static`: Frontend-only apps (React, Vue, Svelte, Astro, etc.) that compile to HTML/CSS/JS. Use this for ANY project that uses `vite`, `webpack`, `next export`, or similar bundlers to produce static files. This is the most common type.
- `node`: Node.js backend servers (Express, Fastify, NestJS, Koa, Hapi) that listen on a port. Only use this for actual server applications, NOT for frontend apps with `vite preview` or `next start`.
- `python`: Python web servers (FastAPI, Flask, Django).
If you created a project with the wrong type, use `update_project` to change it before the next deployment.

## Build Failure Diagnosis & Auto-Fix
After committing code (via `commit_files`) that triggers a deployment:
1. Call `wait_for_deployment` to monitor the build until it completes.
2. If the deployment succeeds, inform the user with the live URL.
3. If the deployment fails:
   a. The wait result includes build logs and error message — analyze the error.
   b. Use `read_file` to examine the source files causing the failure.
   c. Use `commit_files` to push a fix (this auto-triggers a new deployment via webhook).
   d. Call `wait_for_deployment` again to verify the fix worked.
   e. Repeat up to 3 attempts. If still failing, explain the issue to the user.
4. Pushing a commit via `commit_files` auto-triggers deployment via webhook — do NOT call `trigger_deployment` afterward.
"""

# --------------------------------------------------------------------------- #
# Tool definitions (Claude tool-use schema)
# --------------------------------------------------------------------------- #

TOOLS = [
    {
        "name": "list_user_projects",
        "description": "List the user's Miaobu projects with their slugs, types, and domains.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_project_details",
        "description": "Get detailed information about a specific Miaobu project, including build config and repository info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_repo_files",
        "description": "List all files in a GitHub repository. Returns file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (GitHub username)."},
                "repo": {"type": "string", "description": "Repository name."},
                "branch": {"type": "string", "description": "Branch name (optional, defaults to default branch)."},
            },
            "required": ["owner", "repo"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the content of a file from a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "path": {"type": "string", "description": "File path within the repository."},
                "branch": {"type": "string", "description": "Branch name (optional)."},
            },
            "required": ["owner", "repo", "path"],
        },
    },
    {
        "name": "create_repository",
        "description": "Create a new GitHub repository under the user's account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Repository name (lowercase, hyphens, no special chars)."},
                "description": {"type": "string", "description": "Repository description."},
                "private": {"type": "boolean", "description": "Whether the repo should be private. Default false."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "commit_files",
        "description": "Commit multiple files to a GitHub repository in a single commit. Use this to write project files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "branch": {"type": "string", "description": "Target branch (e.g. 'main')."},
                "files": {
                    "type": "array",
                    "description": "Files to commit. Each has 'path' and 'content' (null content = delete).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": ["string", "null"]},
                        },
                        "required": ["path", "content"],
                    },
                },
                "commit_message": {"type": "string", "description": "Commit message."},
            },
            "required": ["owner", "repo", "branch", "files", "commit_message"],
        },
    },
    {
        "name": "create_miaobu_project",
        "description": "Create a Miaobu project from an existing GitHub repository. Sets up webhook and build config.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner."},
                "repo": {"type": "string", "description": "Repository name."},
                "project_type": {
                    "type": "string",
                    "enum": ["static", "node", "python"],
                    "description": "Project type.",
                },
                "build_command": {"type": "string", "description": "Build command (e.g. 'npm run build'). Empty string for no build step."},
                "install_command": {"type": "string", "description": "Install command (e.g. 'npm install')."},
                "output_directory": {"type": "string", "description": "Build output directory (e.g. 'dist'). Only for static projects."},
                "start_command": {"type": "string", "description": "Start command for node/python projects."},
                "node_version": {"type": "string", "description": "Node.js version (e.g. '18', '20')."},
                "python_version": {"type": "string", "description": "Python version (e.g. '3.11')."},
            },
            "required": ["owner", "repo", "project_type"],
        },
    },
    {
        "name": "trigger_deployment",
        "description": "Trigger a deployment for an existing Miaobu project. Fetches latest commit and starts the build pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID to deploy.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "update_project",
        "description": "Update a Miaobu project's settings (project type, build/install/start commands, output directory, etc.). Use this to fix misconfigured projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "project_type": {
                    "type": "string",
                    "enum": ["static", "node", "python"],
                    "description": "Project type: static (frontend apps), node (Node.js servers), python (Python servers).",
                },
                "build_command": {
                    "type": "string",
                    "description": "Build command (e.g., 'npm run build').",
                },
                "install_command": {
                    "type": "string",
                    "description": "Install command (e.g., 'npm install').",
                },
                "output_directory": {
                    "type": "string",
                    "description": "Build output directory (e.g., 'dist').",
                },
                "start_command": {
                    "type": "string",
                    "description": "Start command for node/python projects (e.g., 'node server.js').",
                },
                "node_version": {
                    "type": "string",
                    "description": "Node.js version (e.g., '18', '20').",
                },
                "is_spa": {
                    "type": "boolean",
                    "description": "Whether the static site is a Single Page Application.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_project_deployments",
        "description": "List recent deployments for a project, including status, commit info, error messages, and timing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of deployments to return (default 5, max 20).",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_deployment_logs",
        "description": "Get full build logs and error details for a specific deployment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "deployment_id": {
                    "type": "integer",
                    "description": "The deployment ID.",
                },
            },
            "required": ["project_id", "deployment_id"],
        },
    },
    {
        "name": "wait_for_deployment",
        "description": "Wait for the latest in-progress deployment to reach a terminal state (deployed/failed/cancelled). Polls every 10 seconds, up to 5 minutes. Returns final status, build logs, and error message if failed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "integer",
                    "description": "The Miaobu project ID.",
                },
                "deployment_id": {
                    "type": "integer",
                    "description": "Optional specific deployment ID to wait for. If omitted, waits for the latest in-progress deployment.",
                },
            },
            "required": ["project_id"],
        },
    },
]

# --------------------------------------------------------------------------- #
# Tool executors
# --------------------------------------------------------------------------- #


async def _exec_list_user_projects(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    projects = (
        db.query(Project)
        .filter(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "project_type": p.project_type or "static",
                "domain": p.default_domain,
                "github_repo": p.github_repo_name,
            }
            for p in projects
        ]
    }


async def _exec_get_project_details(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}
    return {
        "id": project.id,
        "name": project.name,
        "slug": project.slug,
        "project_type": project.project_type or "static",
        "github_repo": project.github_repo_name,
        "default_branch": project.default_branch,
        "domain": project.default_domain,
        "build_command": project.build_command,
        "install_command": project.install_command,
        "output_directory": project.output_directory,
        "start_command": project.start_command,
        "node_version": project.node_version,
        "python_version": project.python_version,
    }


async def _exec_list_repo_files(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    files = await GitHubService.get_repository_tree(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input.get("branch"),
    )
    return {"files": files}


async def _exec_read_file(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    content = await GitHubService.get_file_content(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input["path"],
        tool_input.get("branch", "main"),
    )
    if content is None:
        return {"error": f"File not found: {tool_input['path']}"}
    return {"path": tool_input["path"], "content": content}


async def _exec_create_repository(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    repo = await GitHubService.create_repository(
        user.github_access_token,
        tool_input["name"],
        tool_input.get("description", ""),
        tool_input.get("private", False),
        auto_init=True,
    )
    # Wait briefly for GitHub to finish initializing the repo with the initial commit
    await asyncio.sleep(2)
    return {
        "name": repo["name"],
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "default_branch": repo.get("default_branch", "main"),
        "private": repo.get("private", False),
    }


async def _exec_commit_files(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    result = await GitHubService.commit_files(
        user.github_access_token,
        tool_input["owner"],
        tool_input["repo"],
        tool_input["branch"],
        tool_input["files"],
        tool_input["commit_message"],
    )
    return result


async def _exec_create_miaobu_project(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    from ..api.v1.projects import generate_slug

    owner = tool_input["owner"]
    repo_name = tool_input["repo"]
    project_type = tool_input.get("project_type", "static")

    # Fetch repo info from GitHub
    repo_info = await GitHubService.get_repository(
        user.github_access_token, owner, repo_name
    )

    # Check if already imported
    existing = (
        db.query(Project)
        .filter(
            Project.user_id == user.id,
            Project.github_repo_id == repo_info["id"],
            Project.root_directory == "",
        )
        .first()
    )
    if existing:
        return {
            "already_exists": True,
            "project_id": existing.id,
            "slug": existing.slug,
            "domain": existing.default_domain,
        }

    slug = generate_slug(repo_info["name"], user.id, db)

    project_kwargs = dict(
        user_id=user.id,
        github_repo_id=repo_info["id"],
        github_repo_name=repo_info["full_name"],
        github_repo_url=repo_info["html_url"],
        default_branch=repo_info.get("default_branch", "main"),
        name=repo_info["name"],
        slug=slug,
        root_directory="",
        project_type=project_type,
        oss_path=f"projects/{slug}/",
        default_domain=f"{slug}.{settings.cdn_base_domain}",
    )

    if project_type == "static":
        project_kwargs["build_command"] = tool_input.get("build_command", "npm run build")
        project_kwargs["install_command"] = tool_input.get("install_command", "npm install")
        project_kwargs["output_directory"] = tool_input.get("output_directory", "dist")
        project_kwargs["node_version"] = tool_input.get("node_version", "18")
        project_kwargs["is_spa"] = True
    elif project_type == "node":
        project_kwargs["install_command"] = tool_input.get("install_command", "npm install")
        project_kwargs["build_command"] = tool_input.get("build_command", "")
        project_kwargs["start_command"] = tool_input.get("start_command", "node index.js")
        project_kwargs["node_version"] = tool_input.get("node_version", "18")
    elif project_type == "python":
        project_kwargs["python_version"] = tool_input.get("python_version", "3.11")
        project_kwargs["start_command"] = tool_input.get("start_command", "")

    project = Project(**project_kwargs)
    db.add(project)
    db.commit()
    db.refresh(project)

    # Create webhook
    webhook_error = None
    try:
        webhook_secret = secrets.token_urlsafe(32)
        webhook_url = f"{settings.backend_url}/api/v1/webhooks/github/{project.id}"
        webhook = await GitHubService.create_webhook(
            user.github_access_token, owner, repo_name, webhook_url, webhook_secret
        )
        project.webhook_id = webhook["id"]
        project.webhook_secret = webhook_secret
        db.commit()
    except Exception as e:
        webhook_error = str(e)

    return {
        "project_id": project.id,
        "slug": project.slug,
        "domain": project.default_domain,
        "webhook_created": webhook_error is None,
        "webhook_error": webhook_error,
    }


async def _exec_update_project(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    updatable_fields = [
        "project_type", "build_command", "install_command",
        "output_directory", "start_command", "node_version", "is_spa",
    ]
    updated = []
    for field in updatable_fields:
        if field in tool_input:
            old_value = getattr(project, field)
            new_value = tool_input[field]
            setattr(project, field, new_value)
            updated.append(f"{field}: {old_value!r} -> {new_value!r}")

    if not updated:
        return {"error": "No fields to update."}

    db.commit()
    return {
        "project_id": project.id,
        "updated": updated,
        "current_settings": {
            "project_type": project.project_type,
            "build_command": project.build_command,
            "install_command": project.install_command,
            "output_directory": project.output_directory,
            "start_command": project.start_command,
            "node_version": project.node_version,
            "is_spa": project.is_spa,
        },
    }


async def _exec_list_project_deployments(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    limit = min(tool_input.get("limit", 5), 20)
    deployments = (
        db.query(Deployment)
        .filter(Deployment.project_id == project.id)
        .order_by(Deployment.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "project_id": project.id,
        "deployments": [
            {
                "id": d.id,
                "status": d.status.value,
                "commit_sha": d.commit_sha[:8] if d.commit_sha else None,
                "commit_message": d.commit_message,
                "error_message": d.error_message,
                "build_time_seconds": d.build_time_seconds,
                "deployment_url": d.deployment_url,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
            }
            for d in deployments
        ],
    }


async def _exec_get_deployment_logs(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    deployment = (
        db.query(Deployment)
        .filter(
            Deployment.id == tool_input["deployment_id"],
            Deployment.project_id == project.id,
        )
        .first()
    )
    if not deployment:
        return {"error": "Deployment not found."}

    build_logs = deployment.build_logs or ""
    # Truncate to last 8000 chars — errors are at the end
    if len(build_logs) > 8000:
        build_logs = "...(truncated)...\n" + build_logs[-8000:]

    return {
        "deployment_id": deployment.id,
        "status": deployment.status.value,
        "build_logs": build_logs,
        "error_message": deployment.error_message,
    }


async def _exec_wait_for_deployment(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    from ..database import SessionLocal

    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    project_id = project.id
    target_deployment_id = tool_input.get("deployment_id")
    terminal_statuses = {
        DeploymentStatus.DEPLOYED,
        DeploymentStatus.FAILED,
        DeploymentStatus.CANCELLED,
        DeploymentStatus.PURGED,
    }
    max_polls = 30  # 30 * 10s = 5 minutes

    for _ in range(max_polls):
        poll_db = SessionLocal()
        try:
            if target_deployment_id:
                dep = (
                    poll_db.query(Deployment)
                    .filter(
                        Deployment.id == target_deployment_id,
                        Deployment.project_id == project_id,
                    )
                    .first()
                )
            else:
                dep = (
                    poll_db.query(Deployment)
                    .filter(Deployment.project_id == project_id)
                    .order_by(Deployment.created_at.desc())
                    .first()
                )

            if not dep:
                return {"error": "No deployment found for this project."}

            if dep.status in terminal_statuses:
                build_logs = dep.build_logs or ""
                if len(build_logs) > 8000:
                    build_logs = "...(truncated)...\n" + build_logs[-8000:]
                return {
                    "deployment_id": dep.id,
                    "status": dep.status.value,
                    "build_logs": build_logs if dep.status == DeploymentStatus.FAILED else "",
                    "error_message": dep.error_message,
                    "deployment_url": dep.deployment_url,
                    "build_time_seconds": dep.build_time_seconds,
                }
        finally:
            poll_db.close()

        await asyncio.sleep(10)

    # Timeout — return current state
    poll_db = SessionLocal()
    try:
        if target_deployment_id:
            dep = (
                poll_db.query(Deployment)
                .filter(
                    Deployment.id == target_deployment_id,
                    Deployment.project_id == project_id,
                )
                .first()
            )
        else:
            dep = (
                poll_db.query(Deployment)
                .filter(Deployment.project_id == project_id)
                .order_by(Deployment.created_at.desc())
                .first()
            )
        if dep:
            return {
                "deployment_id": dep.id,
                "status": dep.status.value,
                "error_message": dep.error_message,
                "timed_out": True,
                "note": "Deployment did not reach a terminal state within 5 minutes.",
            }
        return {"error": "No deployment found.", "timed_out": True}
    finally:
        poll_db.close()


async def _exec_trigger_deployment(
    tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    project = (
        db.query(Project)
        .filter(Project.id == tool_input["project_id"], Project.user_id == user.id)
        .first()
    )
    if not project:
        return {"error": "Project not found or access denied."}

    owner, repo_name = project.github_repo_name.split("/", 1)

    # Get latest commit
    try:
        async with GitHubService._get_client() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo_name}/branches/{project.default_branch}",
                headers={
                    "Authorization": f"Bearer {user.github_access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            branch_data = response.json()
            commit_sha = branch_data["commit"]["sha"]
            commit_message = branch_data["commit"]["commit"]["message"]
            commit_author = branch_data["commit"]["commit"]["author"]["name"]
    except Exception:
        commit_sha = "manual"
        commit_message = "Deployment triggered by AI"
        commit_author = user.github_username

    deployment = Deployment(
        project_id=project.id,
        commit_sha=commit_sha,
        commit_message=commit_message,
        commit_author=commit_author,
        branch=project.default_branch,
        status=DeploymentStatus.QUEUED,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    result = await trigger_build(project, deployment)
    if not result["success"]:
        return {"error": f"Failed to trigger build: {result['error']}"}

    return {
        "deployment_id": deployment.id,
        "status": "queued",
        "domain": project.default_domain,
        "url": f"https://{project.default_domain}",
    }


# Dispatch table
TOOL_EXECUTORS = {
    "list_user_projects": _exec_list_user_projects,
    "get_project_details": _exec_get_project_details,
    "list_repo_files": _exec_list_repo_files,
    "read_file": _exec_read_file,
    "create_repository": _exec_create_repository,
    "commit_files": _exec_commit_files,
    "create_miaobu_project": _exec_create_miaobu_project,
    "trigger_deployment": _exec_trigger_deployment,
    "update_project": _exec_update_project,
    "list_project_deployments": _exec_list_project_deployments,
    "get_deployment_logs": _exec_get_deployment_logs,
    "wait_for_deployment": _exec_wait_for_deployment,
}


async def _execute_tool(
    tool_name: str, tool_input: Dict[str, Any], user: User, db: Session
) -> Dict[str, Any]:
    """Execute a tool by name with error handling."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await executor(tool_input, user, db)
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Chat orchestration (SSE streaming)
# --------------------------------------------------------------------------- #

MAX_TOOL_ROUNDS = 15
SONNET_MODEL = "claude-sonnet-4-20250514"
OPUS_MODEL = "claude-opus-4-0-20250514"


def _build_messages(session: ChatSession) -> List[Dict[str, Any]]:
    """Build the Claude messages array from persisted session history."""
    messages: List[Dict[str, Any]] = []
    for msg in session.messages:
        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            # Reconstruct content blocks from stored data
            content_blocks: List[Dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            if msg.tool_calls:
                try:
                    tool_calls = json.loads(msg.tool_calls)
                    for tc in tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        })
                except (json.JSONDecodeError, KeyError):
                    pass
            if content_blocks:
                messages.append({"role": "assistant", "content": content_blocks})
            # Append tool results as a user message (Claude API convention)
            if msg.tool_results:
                try:
                    tool_results = json.loads(msg.tool_results)
                    result_blocks = []
                    for tr in tool_results:
                        result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": tr["tool_use_id"],
                            "content": json.dumps(tr["result"], ensure_ascii=False),
                        })
                    if result_blocks:
                        messages.append({"role": "user", "content": result_blocks})
                except (json.JSONDecodeError, KeyError):
                    pass
    return messages


def _sse_event(event_type: str, data: Any) -> str:
    """Format an SSE event."""
    return f"data: {json.dumps({'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"


def prepare_chat(
    session: ChatSession,
    user_message: str,
    user: User,
    db: Session,
) -> Dict[str, Any]:
    """
    Prepare chat context (DB work) before streaming begins.

    Must be called BEFORE creating the StreamingResponse, while the
    SQLAlchemy session is still active. Returns plain data for the generator.
    """
    # Save user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Auto-title from first message
    if session.title == "New chat":
        session.title = user_message[:50].strip()
        db.commit()

    # Build messages from history (while session is still bound)
    messages = _build_messages(session)

    # Extract plain data we'll need inside the generator
    return {
        "session_id": session.id,
        "messages": messages,
        "user_id": user.id,
        "github_access_token": user.github_access_token,
        "github_username": user.github_username,
    }


async def stream_chat(
    ctx: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """
    Main chat orchestration generator. Yields SSE events.

    Uses an asyncio.Queue so that keepalive comments can be sent
    while waiting for Claude API responses, preventing proxy timeouts.
    """
    from ..database import SessionLocal

    session_id = ctx["session_id"]
    messages = ctx["messages"]

    # Build a lightweight user-like object for tool executors
    class _UserCtx:
        def __init__(self, uid, token, username):
            self.id = uid
            self.github_access_token = token
            self.github_username = username

    user_ctx = _UserCtx(ctx["user_id"], ctx["github_access_token"], ctx["github_username"])

    # Configure Anthropic client with proxy if set
    client_kwargs: Dict[str, Any] = {"api_key": settings.anthropic_api_key}
    if settings.http_proxy:
        import httpx as _httpx
        client_kwargs["http_client"] = _httpx.Client(
            proxy=settings.http_proxy,
            timeout=600.0,
        )
    client = anthropic.Anthropic(**client_kwargs)

    accumulated_text = ""
    accumulated_tool_calls: List[Dict[str, Any]] = []
    accumulated_tool_results: List[Dict[str, Any]] = []

    # Queue-based approach: producer pushes events, keepalive task pushes
    # heartbeats, and the generator yields from the queue.
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    producer_done = asyncio.Event()

    async def keepalive():
        """Send SSE comments every 5s to prevent proxy idle-timeout."""
        while not producer_done.is_set():
            await asyncio.sleep(5)
            if not producer_done.is_set():
                await queue.put(": keepalive\n\n")

    async def producer():
        nonlocal accumulated_text, accumulated_tool_calls, accumulated_tool_results
        try:
            await queue.put(_sse_event("stream_start", {}))

            for round_num in range(MAX_TOOL_ROUNDS):
                model = SONNET_MODEL

                response = await asyncio.to_thread(
                    client.messages.create,
                    model=model,
                    max_tokens=16384,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )

                text_parts = []
                tool_use_blocks = []

                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                        await queue.put(_sse_event("text_delta", {"text": block.text}))
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)
                        await queue.put(_sse_event("tool_call_start", {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }))

                round_text = "".join(text_parts)

                if response.stop_reason == "end_turn":
                    accumulated_text += round_text
                    break

                if response.stop_reason == "max_tokens":
                    # Output was truncated — tell Claude so it can retry
                    # with smaller tool calls (e.g., fewer files per commit)
                    accumulated_text += round_text

                    assistant_content = []
                    if round_text:
                        assistant_content.append({"type": "text", "text": round_text})
                    # Include any complete tool_use blocks from truncated response
                    for tb in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tb.id,
                            "name": tb.name,
                            "input": tb.input,
                        })

                    if assistant_content:
                        messages.append({"role": "assistant", "content": assistant_content})

                    # Build tool results for any complete tool blocks
                    truncation_results = []
                    for tb in tool_use_blocks:
                        truncation_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": json.dumps({"error": "Output was truncated (max_tokens reached). Try breaking the operation into smaller steps — e.g., commit files in batches of 3-4 instead of all at once."}, ensure_ascii=False),
                            "is_error": True,
                        })

                    if truncation_results:
                        messages.append({"role": "user", "content": truncation_results})
                    else:
                        # No tool blocks — just tell Claude directly
                        messages.append({"role": "user", "content": [{"type": "text", "text": "[System: Your output was truncated because it exceeded the maximum token limit. Please continue, and if you need to commit many files, do so in smaller batches of 3-4 files per commit.]"}]})

                    await queue.put(_sse_event("text_delta", {"text": "\n\n[输出被截断，正在重试...]\n\n"}))
                    continue

                if response.stop_reason == "tool_use" and tool_use_blocks:
                    tool_results_for_api = []
                    round_tool_calls = []
                    round_tool_results = []

                    for tool_block in tool_use_blocks:
                        # Tool executors that need DB get a fresh session
                        tool_db = SessionLocal()
                        try:
                            result = await _execute_tool(
                                tool_block.name, tool_block.input, user_ctx, tool_db
                            )
                        finally:
                            tool_db.close()

                        await queue.put(_sse_event("tool_call_result", {
                            "id": tool_block.id,
                            "name": tool_block.name,
                            "result": result,
                        }))

                        tool_results_for_api.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                        round_tool_calls.append({
                            "id": tool_block.id,
                            "name": tool_block.name,
                            "input": tool_block.input,
                        })
                        round_tool_results.append({
                            "tool_use_id": tool_block.id,
                            "result": result,
                        })

                    accumulated_tool_calls.extend(round_tool_calls)
                    accumulated_tool_results.extend(round_tool_results)
                    accumulated_text += round_text

                    assistant_content = []
                    if round_text:
                        assistant_content.append({"type": "text", "text": round_text})
                    for tb in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tb.id,
                            "name": tb.name,
                            "input": tb.input,
                        })

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results_for_api})
                else:
                    accumulated_text += round_text
                    break

            # Save assistant message with a fresh DB session
            save_db = SessionLocal()
            try:
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=accumulated_text,
                    tool_calls=json.dumps(accumulated_tool_calls, ensure_ascii=False) if accumulated_tool_calls else None,
                    tool_results=json.dumps(accumulated_tool_results, ensure_ascii=False) if accumulated_tool_results else None,
                )
                save_db.add(assistant_msg)
                save_db.commit()
                save_db.refresh(assistant_msg)
                await queue.put(_sse_event("message_done", {"message_id": assistant_msg.id}))
            finally:
                save_db.close()

        except Exception as e:
            traceback.print_exc()
            await queue.put(_sse_event("error", {"message": str(e)}))
        finally:
            producer_done.set()
            await queue.put(None)  # sentinel to stop consumer

    # Launch producer and keepalive tasks
    producer_task = asyncio.create_task(producer())
    keepalive_task = asyncio.create_task(keepalive())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        keepalive_task.cancel()
        try:
            await producer_task
        except Exception:
            pass
