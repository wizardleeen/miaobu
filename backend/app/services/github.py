import httpx
from typing import Optional, Dict, Any
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
        access_token: str, owner: str, repo: str, branch: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze repository and detect build configuration.

        Returns repository info with auto-detected build settings.
        """
        from .build_detector import BuildDetector

        # Get repository info
        repo_info = await GitHubService.get_repository(access_token, owner, repo)

        if not branch:
            branch = repo_info.get("default_branch", "main")

        # Try to get package.json
        package_json = await GitHubService.get_file_content(
            access_token, owner, repo, "package.json", branch
        )

        if package_json:
            # Detect build configuration from package.json
            build_config = BuildDetector.detect_from_package_json(package_json)
        else:
            # No package.json found, use defaults
            build_config = BuildDetector._get_default_config(
                "unknown",
                "No package.json found - this may not be a Node.js project"
            )

        # Get repository file tree for additional analysis
        files = await GitHubService.get_repository_tree(access_token, owner, repo, branch)
        repo_structure = BuildDetector.analyze_repository_structure(files)

        # Override lock file detection if found in structure
        if repo_structure["lock_file"]:
            if repo_structure["lock_file"] == "yarn":
                build_config["install_command"] = "yarn install"
                build_config["package_manager"] = "yarn"
            elif repo_structure["lock_file"] == "pnpm":
                build_config["install_command"] = "pnpm install"
                build_config["package_manager"] = "pnpm"

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
