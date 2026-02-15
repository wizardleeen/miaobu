import docker
import tempfile
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import hashlib
import redis

from ..config import (
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
        self.docker_client = docker.from_env()
        self.build_dir: Optional[Path] = None
        self.container: Optional[docker.models.containers.Container] = None
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

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT
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
        use_cache: bool = True
    ) -> bool:
        """
        Install dependencies in Docker container.

        Args:
            repo_dir: Repository directory
            install_command: Install command (npm install, yarn install, etc.)
            node_version: Node.js version
            use_cache: Whether to use cached node_modules

        Returns:
            True if successful
        """
        self.log("Installing dependencies...")
        self.log(f"Command: {install_command}")
        self.log(f"Node version: {node_version}")

        try:
            # Check for cached dependencies
            cache_key = None
            cache_restored = False

            if use_cache:
                # Try different lock files
                for lock_file in ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"]:
                    cache_key = self.get_cache_key(repo_dir, lock_file)
                    if cache_key:
                        self.log(f"Cache key from {lock_file}: {cache_key}")
                        cache_path = CACHE_DIR / cache_key

                        if cache_path.exists():
                            self.log(f"✓ Cache hit! Restoring node_modules from cache")
                            # Copy cached node_modules
                            dest = repo_dir / "node_modules"
                            if dest.exists():
                                shutil.rmtree(dest)
                            shutil.copytree(cache_path, dest)
                            cache_restored = True
                            break
                        else:
                            self.log(f"Cache miss for key {cache_key}")
                        break

            if not cache_restored:
                self.log("No cache available, installing from scratch...")

            # Create and run container for installation
            self.log(f"Creating Docker container with Node {node_version}...")

            # Parse install command
            cmd_parts = install_command.split()

            # Run installation in container
            container = self.docker_client.containers.run(
                f"node:{node_version}-alpine",
                command=["sh", "-c", install_command],
                working_dir="/app",
                volumes={
                    str(repo_dir.absolute()): {'bind': '/app', 'mode': 'rw'}
                },
                detach=True,
                remove=False,
                network_mode="bridge"
            )

            self.container = container

            # Stream logs
            for log_line in container.logs(stream=True, follow=True):
                line = log_line.decode('utf-8').strip()
                if line:
                    self.log(line)

            # Wait for completion
            result = container.wait(timeout=INSTALL_TIMEOUT)
            exit_code = result.get('StatusCode', 1)

            # Cleanup container
            container.remove()
            self.container = None

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
        node_version: str
    ) -> Path:
        """
        Run build command in Docker container.

        Args:
            repo_dir: Repository directory
            build_command: Build command to execute
            node_version: Node.js version

        Returns:
            Path to build output directory
        """
        self.log("Running build command...")
        self.log(f"Command: {build_command}")

        try:
            # Create and run container for build
            self.log(f"Creating Docker container with Node {node_version}...")

            container = self.docker_client.containers.run(
                f"node:{node_version}-alpine",
                command=["sh", "-c", build_command],
                working_dir="/app",
                volumes={
                    str(repo_dir.absolute()): {'bind': '/app', 'mode': 'rw'}
                },
                detach=True,
                remove=False,
                network_mode="bridge"
            )

            self.container = container

            # Stream logs
            for log_line in container.logs(stream=True, follow=True):
                line = log_line.decode('utf-8').strip()
                if line:
                    self.log(line)

            # Wait for completion
            result = container.wait(timeout=BUILD_TIMEOUT)
            exit_code = result.get('StatusCode', 1)

            # Cleanup container
            container.remove()
            self.container = None

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
            # Stop container if still running
            if self.container:
                try:
                    self.container.stop(timeout=10)
                    self.container.remove()
                except:
                    pass

            # Remove build directory
            if self.build_dir and self.build_dir.exists():
                self.log(f"Cleaning up build directory: {self.build_dir}")
                shutil.rmtree(self.build_dir, ignore_errors=True)

        except Exception as e:
            self.log(f"Cleanup error: {str(e)}", "WARN")
