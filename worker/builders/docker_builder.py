# import docker  # Disabled due to proxy conflicts
import tempfile
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import hashlib
import redis
import json

from config import (
    TEMP_DIR, CACHE_DIR, BUILD_TIMEOUT, CLONE_TIMEOUT,
    INSTALL_TIMEOUT, REDIS_URL, LOG_STREAM_PREFIX
)


class DockerBuilder:
    """
    Docker-based builder for isolating build processes.

    Responsibilities:
    - Clone repository
    - Create isolated Docker container
    - Execute build commands
    - Capture and stream logs
    - Collect build artifacts
    """

    def __init__(self, deployment_id: int):
        self.deployment_id = deployment_id
        # Note: Using Docker CLI via subprocess instead of docker-py to avoid proxy issues
        self.build_dir: Optional[Path] = None
        self.container_id: Optional[str] = None
        self.log_callback: Optional[Callable] = None

        # Redis for log streaming
        self.redis_client = redis.from_url(REDIS_URL)
        self.log_key = f"{LOG_STREAM_PREFIX}{deployment_id}"

    def set_log_callback(self, callback: Callable[[str], None]):
        """Set callback for log messages."""
        self.log_callback = callback

    def log(self, message: str, level: str = "INFO"):
        """Log a message and stream to Redis."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"

        # Call callback if set
        if self.log_callback:
            self.log_callback(log_line)

        # Stream to Redis for real-time updates
        self.redis_client.rpush(self.log_key, log_line)
        self.redis_client.expire(self.log_key, 3600)  # Expire after 1 hour

        print(log_line)

    def clone_repository(
        self,
        repo_url: str,
        branch: str,
        commit_sha: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Path:
        """
        Clone repository to temporary directory.

        Args:
            repo_url: GitHub repository URL
            branch: Branch to clone
            commit_sha: Specific commit to checkout (optional)
            access_token: GitHub access token for private repos

        Returns:
            Path to cloned repository
        """
        self.log(f"Cloning repository: {repo_url}")
        self.log(f"Branch: {branch}")

        # Create temp directory for this build
        build_id = f"build-{self.deployment_id}-{int(time.time())}"
        self.build_dir = TEMP_DIR / build_id
        self.build_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Construct clone URL with token if provided
            if access_token and "github.com" in repo_url:
                # Convert https://github.com/user/repo to https://token@github.com/user/repo
                clone_url = repo_url.replace("https://", f"https://{access_token}@")
            else:
                clone_url = repo_url

            # Clone repository
            self.log("Running git clone...")
            cmd = [
                "git", "clone",
                "--depth", "1",
                "--branch", branch,
                clone_url,
                str(self.build_dir / "repo")
            ]

            # Set up proxy environment for git
            import os
            env = os.environ.copy()
            # Use HTTP proxy for GitHub access (uses host.docker.internal for dynamic resolution)
            http_proxy = 'http://host.docker.internal:8118'
            env['http_proxy'] = http_proxy
            env['https_proxy'] = http_proxy
            env['HTTP_PROXY'] = http_proxy
            env['HTTPS_PROXY'] = http_proxy
            self.log(f"Using proxy for git: {http_proxy}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT,
                env=env
            )

            if result.returncode != 0:
                raise Exception(f"Git clone failed: {result.stderr}")

            self.log(f"✓ Repository cloned successfully")

            # Checkout specific commit if provided
            if commit_sha:
                self.log(f"Checking out commit: {commit_sha}")
                checkout_cmd = ["git", "checkout", commit_sha]
                result = subprocess.run(
                    checkout_cmd,
                    cwd=self.build_dir / "repo",
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    self.log(f"Warning: Could not checkout {commit_sha}: {result.stderr}", "WARN")
                else:
                    self.log(f"✓ Checked out commit {commit_sha}")

            return self.build_dir / "repo"

        except subprocess.TimeoutExpired:
            raise Exception(f"Clone timeout after {CLONE_TIMEOUT} seconds")
        except Exception as e:
            self.log(f"Clone failed: {str(e)}", "ERROR")
            raise

    def get_cache_key(self, repo_dir: Path, lock_file: str = "package-lock.json") -> Optional[str]:
        """
        Generate cache key from lock file hash.

        Args:
            repo_dir: Repository directory
            lock_file: Lock file name (package-lock.json, yarn.lock, pnpm-lock.yaml)

        Returns:
            MD5 hash of lock file or None if not found
        """
        lock_path = repo_dir / lock_file
        if not lock_path.exists():
            return None

        # Calculate MD5 hash of lock file
        md5 = hashlib.md5()
        with open(lock_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5.update(chunk)

        return md5.hexdigest()

    def install_dependencies(
        self,
        repo_dir: Path,
        install_command: str,
        node_version: str,
        use_cache: bool = True,
        root_directory: str = ""
    ) -> bool:
        """
        Install dependencies in Docker container.

        Args:
            repo_dir: Repository directory
            install_command: Install command (npm install, yarn install, etc.)
            node_version: Node.js version
            use_cache: Whether to use cached node_modules
            root_directory: Subdirectory path for monorepo support (e.g., "frontend")

        Returns:
            True if successful
        """
        self.log("Installing dependencies...")
        self.log(f"Command: {install_command}")
        self.log(f"Node version: {node_version}")
        self.log(f"Repository directory: {repo_dir.absolute()}")
        if root_directory:
            self.log(f"Root directory (monorepo): {root_directory}")

        # Determine working directory path
        work_dir_path = f"{root_directory}/" if root_directory else ""

        # Verify package.json exists
        package_json = repo_dir / root_directory / "package.json" if root_directory else repo_dir / "package.json"
        if not package_json.exists():
            self.log(f"ERROR: package.json not found at {package_json}", "ERROR")
            self.log(f"Directory contents: {list((repo_dir / root_directory).iterdir() if root_directory else repo_dir.iterdir())}", "ERROR")
            raise Exception(f"No package.json found in {package_json}")
        else:
            self.log(f"✓ Found package.json at {package_json}")

        # Note: We trust the project's lock file for dependency resolution
        # No need to modify package.json - if it builds locally, it should build here

        try:
            # TEMPORARILY DISABLE CACHE to ensure clean installs
            # TODO: Re-enable once pnpm script issues are resolved
            cache_key = None
            cache_restored = False
            use_cache = False  # Force disable

            self.log("Cache disabled - installing from scratch...")

            # Create and run container for installation
            self.log(f"Creating Docker container with Node {node_version}...")

            # Parse install command
            cmd_parts = install_command.split()

            # Prepare the command - install pnpm/yarn if needed
            final_command = install_command
            if install_command.startswith("pnpm"):
                # Install pnpm first using corepack (available in Node 16.13+)
                # PNPM 10.x requires explicit approval for build scripts
                # We'll create .npmrc to disable this security check for CI environments
                # Use Taobao npm mirror for faster downloads in China
                final_command = (
                    f"corepack enable && "
                    f"corepack prepare pnpm@latest --activate && "
                    f"echo 'enable-pre-post-scripts=true' > .npmrc && "
                    f"echo 'unsafe-perm=true' >> .npmrc && "
                    f"echo 'ignore-scripts=false' >> .npmrc && "
                    f"echo 'registry=https://registry.npmmirror.com' >> .npmrc && "
                    f"{install_command}"
                )
            elif install_command.startswith("yarn"):
                # Install yarn using corepack
                # Use Taobao npm mirror for faster downloads in China
                final_command = (
                    f"corepack enable && "
                    f"corepack prepare yarn@stable --activate && "
                    f"echo 'registry \"https://registry.npmmirror.com\"' > .yarnrc && "
                    f"{install_command}"
                )
            elif install_command.startswith("npm"):
                # Use Taobao npm mirror for faster downloads in China
                final_command = (
                    f"echo 'registry=https://registry.npmmirror.com' > .npmrc && "
                    f"{install_command}"
                )

            # Run installation using Docker CLI
            # Explicitly unset proxy for npm/pnpm to avoid slow downloads
            # Set working directory to root_directory if specified (for monorepo support)
            docker_work_dir = f"/app/{root_directory}" if root_directory else "/app"
            docker_cmd = [
                "docker", "run",
                "--rm",
                "-e", "HTTP_PROXY=",
                "-e", "HTTPS_PROXY=",
                "-e", "http_proxy=",
                "-e", "https_proxy=",
                "-v", f"{repo_dir.absolute()}:/app",
                "-w", docker_work_dir,
                f"node:{node_version}-alpine",
                "sh", "-c", final_command
            ]

            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Stream logs
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log(line)

            # Wait for completion
            exit_code = process.wait(timeout=INSTALL_TIMEOUT)

            if exit_code != 0:
                raise Exception(f"Install failed with exit code {exit_code}")

            self.log("✓ Dependencies installed successfully")

            # Cache node_modules if we have a cache key
            if cache_key and not cache_restored:
                self.log(f"Caching node_modules with key {cache_key}")
                cache_path = CACHE_DIR / cache_key
                node_modules = repo_dir / "node_modules"

                if node_modules.exists():
                    if cache_path.exists():
                        shutil.rmtree(cache_path)
                    shutil.copytree(node_modules, cache_path)
                    self.log("✓ Dependencies cached for future builds")

            return True

        except subprocess.TimeoutExpired:
            raise Exception(f"Install timeout after {INSTALL_TIMEOUT} seconds")
        except Exception as e:
            self.log(f"Install failed: {str(e)}", "ERROR")
            raise

    def run_build(
        self,
        repo_dir: Path,
        build_command: str,
        node_version: str,
        root_directory: str = ""
    ) -> Path:
        """
        Run build command in Docker container.

        Args:
            repo_dir: Repository directory
            build_command: Build command to execute
            node_version: Node.js version
            root_directory: Subdirectory path for monorepo support (e.g., "frontend")

        Returns:
            Path to build output directory
        """
        self.log("Running build command...")
        self.log(f"Command: {build_command}")
        if root_directory:
            self.log(f"Root directory (monorepo): {root_directory}")

        try:
            # Run build using Docker CLI
            self.log(f"Creating Docker container with Node {node_version}...")

            # Prepare the command - install pnpm/yarn if needed and fix build command
            final_command = build_command

            # Determine the working directory for package manager detection
            work_dir = repo_dir / root_directory if root_directory else repo_dir

            # Detect which package manager was used for installation
            pkg_manager = "npm"  # default
            if (work_dir / "pnpm-lock.yaml").exists():
                pkg_manager = "pnpm"
            elif (work_dir / "yarn.lock").exists():
                pkg_manager = "yarn"

            # If command doesn't start with a package manager, check if it should be run as a script
            if not build_command.startswith(("npm", "pnpm", "yarn", "npx")):
                # Check if there's a matching script in package.json
                import json
                package_json_path = work_dir / "package.json"
                if package_json_path.exists():
                    with open(package_json_path) as f:
                        package_data = json.load(f)
                        scripts = package_data.get("scripts", {})

                        # If the command matches a script name exactly, use it
                        if build_command in scripts:
                            final_command = f"{pkg_manager} run {build_command}"
                        # If command is like "astro build" but there's a "build" script, use "build"
                        elif " " in build_command:
                            cmd_parts = build_command.split()
                            if "build" in scripts and cmd_parts[-1] == "build":
                                final_command = f"{pkg_manager} run build"
                            else:
                                # Try as npm script with full command
                                final_command = f"{pkg_manager} run {build_command}"
                        else:
                            # Try as npm script
                            final_command = f"{pkg_manager} run {build_command}"

            # Install package manager if needed
            if final_command.startswith("pnpm") or pkg_manager == "pnpm":
                # Configure pnpm to allow build scripts and enable proper permissions
                final_command = f"corepack enable && corepack prepare pnpm@latest --activate && pnpm config set enable-pre-post-scripts true && pnpm config set unsafe-perm true && pnpm config set shamefully-hoist true && {final_command}"
            elif final_command.startswith("yarn") or pkg_manager == "yarn":
                final_command = f"corepack enable && corepack prepare yarn@stable --activate && {final_command}"

            # Unset proxy for npm/pnpm to avoid slow downloads
            # Add environment variables for better build compatibility
            # Set working directory to root_directory if specified (for monorepo support)
            docker_work_dir = f"/app/{root_directory}" if root_directory else "/app"
            docker_cmd = [
                "docker", "run",
                "--rm",
                "-e", "HTTP_PROXY=",
                "-e", "HTTPS_PROXY=",
                "-e", "http_proxy=",
                "-e", "https_proxy=",
                "-e", "ASTRO_TELEMETRY_DISABLED=1",  # Disable Astro telemetry
                "-e", "NODE_ENV=production",          # Set production environment
                "-e", "CI=true",                      # Indicate CI environment
                "-e", "NO_COLOR=1",                   # Disable color output for cleaner logs
                "-v", f"{repo_dir.absolute()}:/app",
                "-w", docker_work_dir,
                f"node:{node_version}-alpine",
                "sh", "-c", final_command
            ]

            process = subprocess.Popen(
                docker_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Stream logs
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log(line)

            # Wait for completion
            exit_code = process.wait(timeout=BUILD_TIMEOUT)

            if exit_code != 0:
                raise Exception(f"Build failed with exit code {exit_code}")

            self.log("✓ Build completed successfully")

            return repo_dir

        except subprocess.TimeoutExpired:
            raise Exception(f"Build timeout after {BUILD_TIMEOUT} seconds")
        except Exception as e:
            self.log(f"Build failed: {str(e)}", "ERROR")
            raise

    def cleanup(self):
        """Cleanup build directory and resources."""
        try:
            # Stop container if still running (using container_id)
            if self.container_id:
                try:
                    subprocess.run(["docker", "stop", self.container_id], timeout=10, capture_output=True)
                    subprocess.run(["docker", "rm", self.container_id], timeout=10, capture_output=True)
                except:
                    pass

            # Remove build directory
            if self.build_dir and self.build_dir.exists():
                self.log(f"Cleaning up build directory: {self.build_dir}")
                shutil.rmtree(self.build_dir, ignore_errors=True)

        except Exception as e:
            self.log(f"Cleanup error: {str(e)}", "WARN")
