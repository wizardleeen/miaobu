import asyncio
import base64
import httpx
from typing import Optional, Dict, Any, List
from ..config import get_settings

settings = get_settings()


class GitHubService:
    """Service for interacting with GitHub API."""

    GITHUB_API_URL = "https://api.github.com"
    GITHUB_OAUTH_URL = "https://github.com/login/oauth"

    @staticmethod
    def _get_client(timeout: float = 30.0) -> httpx.AsyncClient:
        """Get configured HTTP client with proxy support."""
        client_kwargs = {"timeout": timeout}
        if settings.http_proxy:
            client_kwargs["proxies"] = settings.http_proxy
        return httpx.AsyncClient(**client_kwargs)

    @staticmethod
    async def get_oauth_url(state: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        return (
            f"{GitHubService.GITHUB_OAUTH_URL}/authorize"
            f"?client_id={settings.github_client_id}"
            f"&redirect_uri={settings.github_redirect_uri}"
            f"&scope=repo,read:user,user:email"
            f"&state={state}"
        )

    @staticmethod
    async def exchange_code_for_token(code: str) -> str:
        """Exchange authorization code for access token."""
        async with GitHubService._get_client() as client:
            response = await client.post(
                f"{GitHubService.GITHUB_OAUTH_URL}/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                raise Exception(f"GitHub OAuth error: {data.get('error')} - {data.get('error_description', '')}")
            return data.get("access_token")

    @staticmethod
    async def get_user_info(access_token: str) -> Dict[str, Any]:
        """Get authenticated user's information from GitHub."""
        async with GitHubService._get_client() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            user_data = response.json()

            # Get user's primary email if not public
            if not user_data.get("email"):
                email_response = await client.get(
                    f"{GitHubService.GITHUB_API_URL}/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary_email = next(
                        (e["email"] for e in emails if e.get("primary")),
                        None
                    )
                    user_data["email"] = primary_email

            return user_data

    @staticmethod
    async def list_repositories(access_token: str, page: int = 1, per_page: int = 30) -> list:
        """List user's repositories."""
        async with GitHubService._get_client() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params={
                    "sort": "updated",
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def get_repository(access_token: str, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository information."""
        async with GitHubService._get_client() as client:
            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def get_file_content(
        access_token: str, owner: str, repo: str, file_path: str, branch: str = "main"
    ) -> Optional[str]:
        """Get file content from repository."""
        async with GitHubService._get_client() as client:
            try:
                response = await client.get(
                    f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3.raw",
                    },
                    params={"ref": branch},
                )
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError:
                return None

    @staticmethod
    async def create_webhook(
        access_token: str, owner: str, repo: str, webhook_url: str, secret: str
    ) -> Dict[str, Any]:
        """Create a webhook for repository."""
        async with GitHubService._get_client() as client:
            response = await client.post(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/hooks",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "name": "web",
                    "active": True,
                    "events": ["push"],
                    "config": {
                        "url": webhook_url,
                        "content_type": "json",
                        "secret": secret,
                        "insecure_ssl": "0",
                    },
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def delete_webhook(access_token: str, owner: str, repo: str, hook_id: int) -> bool:
        """Delete a webhook from repository."""
        async with GitHubService._get_client() as client:
            try:
                response = await client.delete(
                    f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/hooks/{hook_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                response.raise_for_status()
                return True
            except httpx.HTTPStatusError:
                return False

    @staticmethod
    async def get_repository_tree(
        access_token: str, owner: str, repo: str, branch: Optional[str] = None
    ) -> list:
        """Get repository file tree."""
        async with GitHubService._get_client() as client:
            try:
                # First get the default branch if not specified
                if not branch:
                    repo_info = await GitHubService.get_repository(access_token, owner, repo)
                    branch = repo_info.get("default_branch", "main")

                # Get tree
                response = await client.get(
                    f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/{branch}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"recursive": "1"},
                )
                response.raise_for_status()
                data = response.json()
                return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
            except httpx.HTTPStatusError:
                return []

    @staticmethod
    async def analyze_repository(
        access_token: str, owner: str, repo: str, branch: Optional[str] = None, root_directory: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze repository and detect build configuration.

        Args:
            access_token: GitHub access token
            owner: Repository owner
            repo: Repository name
            branch: Branch name (defaults to default branch)
            root_directory: Subdirectory path for monorepo support (e.g., "frontend")

        Returns repository info with auto-detected build settings.
        """
        from .build_detector import BuildDetector

        # Get repository info
        repo_info = await GitHubService.get_repository(access_token, owner, repo)

        if not branch:
            branch = repo_info.get("default_branch", "main")

        # Construct file paths with root_directory
        def get_path(filename: str) -> str:
            return f"{root_directory}/{filename}" if root_directory else filename

        # Get repository file tree for structure analysis
        files = await GitHubService.get_repository_tree(access_token, owner, repo, branch)
        repo_structure = BuildDetector.analyze_repository_structure(files, root_directory)

        # Detect project type (static/Node.js vs Python)
        project_type = BuildDetector.detect_project_type(files, root_directory)

        if project_type == "python":
            # Python project detection
            requirements_path = get_path("requirements.txt")
            pyproject_path = get_path("pyproject.toml")
            pipfile_path = get_path("Pipfile")
            python_version_path = get_path(".python-version")

            requirements, pyproject, pipfile, python_version_file = await asyncio.gather(
                GitHubService.get_file_content(access_token, owner, repo, requirements_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, pyproject_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, pipfile_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, python_version_path, branch),
            )

            build_config = BuildDetector.detect_from_python_project(
                requirements_content=requirements,
                pyproject_content=pyproject,
                pipfile_content=pipfile,
            )

            python_version = BuildDetector.detect_python_version(
                python_version_file=python_version_file,
                pyproject_content=pyproject,
            )
            build_config["python_version"] = python_version

        else:
            # Node.js / static project detection
            package_json_path = get_path("package.json")
            nvmrc_path = get_path(".nvmrc")
            node_version_path = get_path(".node-version")
            netlify_toml_path = get_path("netlify.toml")
            vercel_json_path = get_path("vercel.json")

            package_json, nvmrc, node_version_file, netlify_toml, vercel_json = await asyncio.gather(
                GitHubService.get_file_content(access_token, owner, repo, package_json_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, nvmrc_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, node_version_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, netlify_toml_path, branch),
                GitHubService.get_file_content(access_token, owner, repo, vercel_json_path, branch),
            )

            # Check if this is a Node.js backend project
            node_backend_config = None
            if package_json:
                node_backend_config = BuildDetector.detect_from_node_backend(package_json)

            if node_backend_config:
                # Node.js backend project
                project_type = "node"
                build_config = node_backend_config

                node_version = BuildDetector.detect_node_version_from_files(
                    package_json=package_json,
                    nvmrc=nvmrc,
                    node_version_file=node_version_file,
                    netlify_toml=netlify_toml,
                    vercel_json=vercel_json
                )
                build_config["node_version"] = node_version

                # Override install/build commands based on lockfile
                if repo_structure["lock_file"]:
                    if repo_structure["lock_file"] == "yarn":
                        build_config["install_command"] = "yarn install"
                        if build_config.get("build_command"):
                            build_config["build_command"] = "yarn run build"
                        build_config["package_manager"] = "yarn"
                    elif repo_structure["lock_file"] == "pnpm":
                        build_config["install_command"] = "pnpm install"
                        if build_config.get("build_command"):
                            build_config["build_command"] = "pnpm run build"
                        build_config["package_manager"] = "pnpm"

            elif package_json:
                build_config = BuildDetector.detect_from_package_json(package_json)

                node_version = BuildDetector.detect_node_version_from_files(
                    package_json=package_json,
                    nvmrc=nvmrc,
                    node_version_file=node_version_file,
                    netlify_toml=netlify_toml,
                    vercel_json=vercel_json
                )
                build_config["node_version"] = node_version

                detection_sources = []
                if nvmrc:
                    detection_sources.append(".nvmrc")
                if node_version_file:
                    detection_sources.append(".node-version")
                if netlify_toml and "NODE_VERSION" in netlify_toml:
                    detection_sources.append("netlify.toml")
                if vercel_json:
                    detection_sources.append("vercel.json")

                build_config["node_version_source"] = detection_sources[0] if detection_sources else "default"
                build_config["project_type"] = "static"

                # Override install/build commands based on lockfile
                if repo_structure["lock_file"]:
                    if repo_structure["lock_file"] == "yarn":
                        build_config["install_command"] = "yarn install"
                        build_config["build_command"] = "yarn run build"
                        build_config["package_manager"] = "yarn"
                    elif repo_structure["lock_file"] == "pnpm":
                        build_config["install_command"] = "pnpm install"
                        build_config["build_command"] = "pnpm run build"
                        build_config["package_manager"] = "pnpm"
            else:
                not_found_msg = f"No package.json found at {package_json_path}" if root_directory else "No package.json found - this may not be a Node.js project"
                build_config = BuildDetector._get_default_config(
                    "unknown",
                    not_found_msg
                )
                build_config["project_type"] = "static"

        return {
            "repository": {
                "id": repo_info["id"],
                "name": repo_info["name"],
                "full_name": repo_info["full_name"],
                "html_url": repo_info["html_url"],
                "clone_url": repo_info["clone_url"],
                "default_branch": branch,
                "description": repo_info.get("description"),
                "language": repo_info.get("language"),
                "private": repo_info.get("private", False),
                "updated_at": repo_info.get("updated_at"),
            },
            "build_config": build_config,
            "repo_structure": repo_structure,
            "root_directory": root_directory,
            "project_type": project_type,
        }

    @staticmethod
    async def create_repository(
        access_token: str, name: str, description: str = "", private: bool = False, auto_init: bool = True
    ) -> Dict[str, Any]:
        """Create a new GitHub repository under the authenticated user's account."""
        async with GitHubService._get_client() as client:
            response = await client.post(
                f"{GitHubService.GITHUB_API_URL}/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={
                    "name": name,
                    "description": description,
                    "private": private,
                    "auto_init": auto_init,
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def commit_files(
        access_token: str, owner: str, repo: str, branch: str,
        files: List[Dict[str, Any]], commit_message: str
    ) -> Dict[str, Any]:
        """
        Commit multiple files in a single commit using the Git Trees API.

        Args:
            files: List of {"path": "...", "content": "..."} dicts.
                   content=None means delete the file.
        """
        async with GitHubService._get_client(timeout=60.0) as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            }

            # 1. Get the current branch ref
            ref_response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{branch}",
                headers=headers,
            )
            ref_response.raise_for_status()
            current_sha = ref_response.json()["object"]["sha"]

            # 2. Get the current commit's tree SHA
            commit_response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/commits/{current_sha}",
                headers=headers,
            )
            commit_response.raise_for_status()
            base_tree_sha = commit_response.json()["tree"]["sha"]

            # 3. Create blobs for each file and build tree entries
            tree_items = []
            for file in files:
                if file.get("content") is None:
                    # Delete file by omitting from tree (handled by not using base_tree for this path)
                    tree_items.append({
                        "path": file["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": None,
                    })
                else:
                    # Create blob
                    blob_response = await client.post(
                        f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/blobs",
                        headers=headers,
                        json={
                            "content": file["content"],
                            "encoding": "utf-8",
                        },
                    )
                    blob_response.raise_for_status()
                    blob_sha = blob_response.json()["sha"]
                    tree_items.append({
                        "path": file["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    })

            # 4. Create new tree with base_tree
            tree_response = await client.post(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/trees",
                headers=headers,
                json={
                    "base_tree": base_tree_sha,
                    "tree": tree_items,
                },
            )
            tree_response.raise_for_status()
            new_tree_sha = tree_response.json()["sha"]

            # 5. Create commit
            new_commit_response = await client.post(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/commits",
                headers=headers,
                json={
                    "message": commit_message,
                    "tree": new_tree_sha,
                    "parents": [current_sha],
                },
            )
            new_commit_response.raise_for_status()
            new_commit_sha = new_commit_response.json()["sha"]

            # 6. Update branch ref
            update_ref_response = await client.patch(
                f"{GitHubService.GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{branch}",
                headers=headers,
                json={"sha": new_commit_sha},
            )
            update_ref_response.raise_for_status()

            return {
                "sha": new_commit_sha,
                "message": commit_message,
                "files_changed": len(files),
            }

    @staticmethod
    async def search_repositories(
        access_token: str, query: str, page: int = 1, per_page: int = 30
    ) -> Dict[str, Any]:
        """Search user's repositories."""
        async with GitHubService._get_client() as client:
            # Get current user to filter by ownership
            user_info = await GitHubService.get_user_info(access_token)
            username = user_info["login"]

            search_query = f"{query} user:{username}"

            response = await client.get(
                f"{GitHubService.GITHUB_API_URL}/search/repositories",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                params={
                    "q": search_query,
                    "sort": "updated",
                    "per_page": per_page,
                    "page": page,
                },
            )
            response.raise_for_status()
            return response.json()
