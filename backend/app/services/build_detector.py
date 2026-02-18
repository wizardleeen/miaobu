import json
from typing import Dict, Optional, Any
import re


class BuildDetector:
    """Service for detecting build configuration from repository files."""

    # Python framework detection patterns
    PYTHON_FRAMEWORK_PATTERNS = {
        "fastapi": {
            "indicators": ["fastapi", "uvicorn"],
            "start_command": "uvicorn main:app --host 0.0.0.0 --port 9000",
            "framework": "fastapi",
        },
        "flask": {
            "indicators": ["flask"],
            "start_command": "gunicorn --bind 0.0.0.0:9000 app:app",
            "framework": "flask",
        },
        "django": {
            "indicators": ["django"],
            "start_command": "gunicorn --bind 0.0.0.0:9000 config.wsgi:application",
            "framework": "django",
        },
    }

    # Node.js backend framework detection patterns
    NODE_BACKEND_FRAMEWORK_PATTERNS = {
        "express": {
            "indicators": ["express"],
            "start_command": "node index.js",
            "framework": "express",
        },
        "fastify": {
            "indicators": ["fastify"],
            "start_command": "node index.js",
            "framework": "fastify",
        },
        "nestjs": {
            "indicators": ["@nestjs/core"],
            "start_command": "node dist/main.js",
            "framework": "nestjs",
            "needs_build": True,
        },
        "koa": {
            "indicators": ["koa"],
            "start_command": "node index.js",
            "framework": "koa",
        },
        "hapi": {
            "indicators": ["@hapi/hapi"],
            "start_command": "node index.js",
            "framework": "hapi",
        },
    }

    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "slidev": {
            "indicators": ["@slidev/cli"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "is_spa": False
        },
        "astro": {
            "indicators": ["astro"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "is_spa": False
        },
        "vite": {
            "indicators": ["vite", "@vitejs/plugin-react"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "is_spa": True
        },
        "create-react-app": {
            "indicators": ["react-scripts"],
            "build_command": "npm run build",
            "output_directory": "build",
            "dev_command": "npm start",
            "is_spa": True
        },
        "next": {
            "indicators": ["next"],
            "build_command": "npm run build && npm run export",
            "output_directory": "out",
            "dev_command": "npm run dev",
            "note": "Requires static export configuration",
            "is_spa": False
        },
        "vue-cli": {
            "indicators": ["@vue/cli-service"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run serve",
            "is_spa": True
        },
        "nuxt": {
            "indicators": ["nuxt"],
            "build_command": "npm run generate",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "is_spa": False
        },
        "gatsby": {
            "indicators": ["gatsby"],
            "build_command": "npm run build",
            "output_directory": "public",
            "dev_command": "npm run develop",
            "is_spa": False
        },
        "angular": {
            "indicators": ["@angular/cli"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "ng serve",
            "is_spa": True
        },
        "svelte": {
            "indicators": ["svelte"],
            "build_command": "npm run build",
            "output_directory": "public/build",
            "dev_command": "npm run dev",
            "is_spa": True
        },
        "docusaurus": {
            "indicators": ["@docusaurus/core"],
            "build_command": "npm run build",
            "output_directory": "build",
            "dev_command": "npm run start",
            "is_spa": False
        },
        "vuepress": {
            "indicators": ["vuepress"],
            "build_command": "npm run build",
            "output_directory": "docs/.vuepress/dist",
            "dev_command": "npm run dev",
            "is_spa": False
        }
    }

    @staticmethod
    def detect_from_package_json(package_json_content: str) -> Dict[str, Any]:
        """
        Detect build configuration from package.json content.

        Args:
            package_json_content: Raw content of package.json file

        Returns:
            Dictionary with detected build configuration
        """
        try:
            package_data = json.loads(package_json_content)
        except json.JSONDecodeError:
            return BuildDetector._get_default_config("unknown", "Invalid package.json")

        # Get dependencies
        dependencies = package_data.get("dependencies", {})
        dev_dependencies = package_data.get("devDependencies", {})
        all_deps = {**dependencies, **dev_dependencies}
        scripts = package_data.get("scripts", {})

        # Detect framework
        detected_framework = None
        framework_config = None

        for framework_name, config in BuildDetector.FRAMEWORK_PATTERNS.items():
            for indicator in config["indicators"]:
                if indicator in all_deps:
                    detected_framework = framework_name
                    framework_config = config
                    break
            if detected_framework:
                break

        # If no framework detected, try to infer from scripts
        if not detected_framework:
            if "next" in scripts.get("dev", ""):
                detected_framework = "next"
                framework_config = BuildDetector.FRAMEWORK_PATTERNS["next"]
            elif "vite" in scripts.get("dev", ""):
                detected_framework = "vite"
                framework_config = BuildDetector.FRAMEWORK_PATTERNS["vite"]
            elif "gatsby" in scripts.get("develop", ""):
                detected_framework = "gatsby"
                framework_config = BuildDetector.FRAMEWORK_PATTERNS["gatsby"]

        # Use detected framework or defaults
        if framework_config:
            build_command = framework_config["build_command"]
            output_directory = framework_config["output_directory"]
            dev_command = framework_config.get("dev_command", "npm run dev")
            note = framework_config.get("note")
            is_spa = framework_config.get("is_spa", True)
        else:
            # Try to infer from scripts
            build_command = scripts.get("build", "npm run build")
            output_directory = BuildDetector._guess_output_directory(build_command, all_deps)
            dev_command = scripts.get("dev") or scripts.get("start", "npm start")
            note = None
            is_spa = True  # Default to SPA for unknown frameworks

        # Detect Node version from engines
        node_version = BuildDetector._detect_node_version(package_data)

        # Detect install command (npm, yarn, pnpm)
        install_command = BuildDetector._detect_install_command(package_data)

        return {
            "framework": detected_framework or "unknown",
            "build_command": build_command,
            "install_command": install_command,
            "output_directory": output_directory,
            "dev_command": dev_command,
            "node_version": node_version,
            "is_spa": is_spa,
            "has_typescript": "typescript" in all_deps,
            "package_manager": BuildDetector._detect_package_manager(package_data),
            "scripts": scripts,
            "note": note,
            "confidence": "high" if detected_framework else "medium"
        }

    @staticmethod
    def _detect_node_version(package_data: Dict) -> str:
        """Detect required Node.js version from package.json engines field."""
        engines = package_data.get("engines", {})
        node_version = engines.get("node", "")

        if node_version:
            return BuildDetector._normalize_node_version(node_version)

        # No version found in package.json
        return None

    @staticmethod
    def _normalize_node_version(version_string: str) -> Optional[str]:
        """
        Normalize a Node version string to a major version number.

        Examples:
            ">=20.0.0" -> "20"
            "^18.0.0" -> "18"
            "20" -> "20"
            "v20.1.0" -> "20"
        """
        if not version_string:
            return None

        # Extract version number (e.g., ">=16.0.0" -> "16", "^18.0.0" -> "18", "v20" -> "20")
        match = re.search(r"(\d+)", str(version_string))
        if match:
            version = match.group(1)
            version_num = int(version)

            # Map to supported versions
            if version_num >= 20:
                return "20"
            elif version_num >= 18:
                return "18"
            elif version_num >= 16:
                return "16"
            elif version_num >= 14:
                return "14"

        return None

    @staticmethod
    def detect_node_version_from_files(
        package_json: Optional[str] = None,
        nvmrc: Optional[str] = None,
        node_version_file: Optional[str] = None,
        netlify_toml: Optional[str] = None,
        vercel_json: Optional[str] = None
    ) -> str:
        """
        Detect Node version from multiple sources, with priority order:
        1. .nvmrc (most explicit for development)
        2. .node-version (nodenv standard)
        3. package.json engines.node
        4. netlify.toml
        5. vercel.json
        6. Default to 18 (LTS)

        Args:
            package_json: Content of package.json
            nvmrc: Content of .nvmrc file
            node_version_file: Content of .node-version file
            netlify_toml: Content of netlify.toml
            vercel_json: Content of vercel.json

        Returns:
            Node version string (e.g., "20", "18", "16")
        """
        # Priority 1: .nvmrc
        if nvmrc:
            version = BuildDetector._parse_nvmrc(nvmrc)
            if version:
                return version

        # Priority 2: .node-version
        if node_version_file:
            version = BuildDetector._parse_node_version_file(node_version_file)
            if version:
                return version

        # Priority 3: package.json engines.node
        if package_json:
            try:
                package_data = json.loads(package_json)
                version = BuildDetector._detect_node_version(package_data)
                if version:
                    return version
            except (json.JSONDecodeError, Exception):
                pass

        # Priority 4: netlify.toml
        if netlify_toml:
            version = BuildDetector._parse_netlify_toml(netlify_toml)
            if version:
                return version

        # Priority 5: vercel.json
        if vercel_json:
            version = BuildDetector._parse_vercel_json(vercel_json)
            if version:
                return version

        # Default to 18 (LTS)
        return "18"

    @staticmethod
    def _parse_nvmrc(content: str) -> Optional[str]:
        """Parse .nvmrc file content."""
        # .nvmrc typically contains just the version, e.g., "20.1.0" or "v20" or "lts/iron"
        content = content.strip()

        # Handle LTS codenames
        lts_mapping = {
            "lts/iron": "20",
            "lts/hydrogen": "18",
            "lts/gallium": "16",
        }

        if content.lower() in lts_mapping:
            return lts_mapping[content.lower()]

        return BuildDetector._normalize_node_version(content)

    @staticmethod
    def _parse_node_version_file(content: str) -> Optional[str]:
        """Parse .node-version file content."""
        # Similar to .nvmrc
        return BuildDetector._normalize_node_version(content.strip())

    @staticmethod
    def _parse_netlify_toml(content: str) -> Optional[str]:
        """Parse netlify.toml for NODE_VERSION."""
        # Look for NODE_VERSION = "20" in [build.environment] section
        # Simple regex-based parsing (could use toml library for robustness)
        match = re.search(r'NODE_VERSION\s*=\s*["\']?(\d+)["\']?', content, re.IGNORECASE)
        if match:
            return BuildDetector._normalize_node_version(match.group(1))
        return None

    @staticmethod
    def _parse_vercel_json(content: str) -> Optional[str]:
        """Parse vercel.json for Node version."""
        try:
            data = json.loads(content)

            # Check build.env.NODE_VERSION
            node_version = data.get("build", {}).get("env", {}).get("NODE_VERSION")
            if node_version:
                return BuildDetector._normalize_node_version(str(node_version))

            # Check buildCommand with NODE_VERSION
            build_command = data.get("buildCommand", "")
            match = re.search(r'NODE_VERSION=(\d+)', build_command)
            if match:
                return BuildDetector._normalize_node_version(match.group(1))

        except (json.JSONDecodeError, Exception):
            pass

        return None

    @staticmethod
    def _detect_package_manager(package_data: Dict) -> str:
        """Detect package manager from package.json."""
        if "packageManager" in package_data:
            pm = package_data["packageManager"]
            if "pnpm" in pm:
                return "pnpm"
            elif "yarn" in pm:
                return "yarn"

        # Check for lock files would be done in repo analysis
        return "npm"

    @staticmethod
    def _detect_install_command(package_data: Dict) -> str:
        """Detect appropriate install command."""
        pm = BuildDetector._detect_package_manager(package_data)

        if pm == "pnpm":
            return "pnpm install"
        elif pm == "yarn":
            return "yarn install"
        else:
            return "npm install"

    @staticmethod
    def _guess_output_directory(build_command: str, dependencies: Dict) -> str:
        """Guess output directory based on build command and dependencies."""
        # Check build command for output hints
        if "out" in build_command.lower():
            return "out"
        if "public" in build_command.lower():
            return "public"
        if "build" in build_command.lower():
            return "build"

        # Check dependencies for framework hints
        if "next" in dependencies:
            return "out"
        if "gatsby" in dependencies:
            return "public"
        if "react-scripts" in dependencies:
            return "build"

        # Default
        return "dist"

    @staticmethod
    def detect_project_type(files: list, root_directory: str = "") -> str:
        """
        Detect whether a repository is a static/Node.js project or a Python project.

        Args:
            files: List of file paths in the repository
            root_directory: Subdirectory path for monorepo support

        Returns:
            "python" or "static"
        """
        root_dir = root_directory.strip("/") if root_directory else ""
        prefix = f"{root_dir}/" if root_dir else ""

        python_indicators = [
            "requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg"
        ]
        node_indicators = ["package.json"]

        has_python = False
        has_node = False

        for file_path in files:
            if root_dir and not file_path.startswith(prefix):
                continue

            relative_path = file_path[len(prefix):] if prefix else file_path

            # Only check root-level files
            if "/" in relative_path:
                continue

            if relative_path in python_indicators:
                has_python = True
            if relative_path in node_indicators:
                has_node = True

        # If both exist, prefer Node (might be a fullstack project with Python tooling)
        # If only Python indicators exist, it's a Python project
        if has_python and not has_node:
            return "python"

        return "static"

    @staticmethod
    def detect_from_python_project(
        requirements_content: Optional[str] = None,
        pyproject_content: Optional[str] = None,
        pipfile_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detect Python framework and build configuration from dependency files.

        Args:
            requirements_content: Content of requirements.txt
            pyproject_content: Content of pyproject.toml
            pipfile_content: Content of Pipfile

        Returns:
            Dictionary with detected Python build configuration
        """
        # Collect all dependency names
        deps = set()

        if requirements_content:
            for line in requirements_content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    # Extract package name (before any version specifier)
                    pkg = re.split(r'[><=!~\[]', line)[0].strip().lower()
                    if pkg:
                        deps.add(pkg)

        if pyproject_content:
            # Simple parsing for [project] dependencies
            in_deps = False
            for line in pyproject_content.splitlines():
                if re.match(r'\s*dependencies\s*=\s*\[', line):
                    in_deps = True
                    continue
                if in_deps:
                    if ']' in line:
                        in_deps = False
                    pkg_match = re.search(r'"([^"]+)"', line)
                    if pkg_match:
                        pkg = re.split(r'[><=!~\[]', pkg_match.group(1))[0].strip().lower()
                        if pkg:
                            deps.add(pkg)

        if pipfile_content:
            in_packages = False
            for line in pipfile_content.splitlines():
                if line.strip() == '[packages]':
                    in_packages = True
                    continue
                if line.strip().startswith('[') and in_packages:
                    in_packages = False
                    continue
                if in_packages and '=' in line:
                    pkg = line.split('=')[0].strip().lower().strip('"')
                    if pkg:
                        deps.add(pkg)

        # Detect framework
        detected_framework = None
        start_command = None

        for framework_name, config in BuildDetector.PYTHON_FRAMEWORK_PATTERNS.items():
            for indicator in config["indicators"]:
                if indicator in deps:
                    detected_framework = config["framework"]
                    start_command = config["start_command"]
                    break
            if detected_framework:
                break

        # Default start command if no framework detected
        if not start_command:
            start_command = "python main.py"

        return {
            "project_type": "python",
            "framework": detected_framework or "python",
            "python_framework": detected_framework,
            "start_command": start_command,
            "dependencies": list(deps),
            "confidence": "high" if detected_framework else "medium",
        }

    @staticmethod
    def detect_from_node_backend(package_json_content: str) -> Optional[Dict[str, Any]]:
        """
        Detect Node.js backend framework from package.json content.

        Returns config dict if a backend framework is detected, None otherwise.
        """
        try:
            package_data = json.loads(package_json_content)
        except json.JSONDecodeError:
            return None

        dependencies = package_data.get("dependencies", {})
        dev_dependencies = package_data.get("devDependencies", {})
        all_deps = {**dependencies, **dev_dependencies}
        scripts = package_data.get("scripts", {})

        # Check for Node.js backend frameworks
        detected_framework = None
        framework_config = None

        for framework_name, config in BuildDetector.NODE_BACKEND_FRAMEWORK_PATTERNS.items():
            for indicator in config["indicators"]:
                if indicator in dependencies:  # Only check production deps
                    detected_framework = framework_name
                    framework_config = config
                    break
            if detected_framework:
                break

        if not detected_framework:
            # Fallback: detect plain Node.js server (no framework)
            # If scripts.start looks like a server command and there are no
            # frontend framework indicators, treat as node backend
            start_script = scripts.get("start", "")
            has_frontend_framework = any(
                indicator in all_deps
                for config in BuildDetector.FRAMEWORK_PATTERNS.values()
                for indicator in config["indicators"]
            )
            is_server_start = (
                start_script.startswith("node ")
                or start_script.startswith("ts-node ")
                or start_script.startswith("nodemon ")
                or "server" in start_script.lower()
            )
            if is_server_start and not has_frontend_framework:
                detected_framework = "node"
                framework_config = {
                    "start_command": start_script,
                    "framework": "node",
                }
            else:
                return None

        # Determine start command: prefer the actual value from scripts.start
        # (not "npm start" — npm doesn't work reliably in FC layer environment)
        if scripts.get("start"):
            start_command = scripts["start"]
        else:
            start_command = framework_config["start_command"]

        # Determine build command
        build_command = ""
        needs_build = framework_config.get("needs_build", False)
        has_typescript = "typescript" in all_deps
        if (needs_build or has_typescript) and scripts.get("build"):
            build_command = "npm run build"

        # Detect install command and node version
        install_command = BuildDetector._detect_install_command(package_data)
        node_version = BuildDetector._detect_node_version(package_data)

        return {
            "project_type": "node",
            "framework": detected_framework,
            "start_command": start_command,
            "install_command": install_command,
            "build_command": build_command,
            "node_version": node_version,
            "confidence": "high",
        }

    @staticmethod
    def detect_python_version(
        python_version_file: Optional[str] = None,
        pyproject_content: Optional[str] = None,
    ) -> str:
        """
        Detect Python version from project files.

        Priority:
        1. .python-version file
        2. pyproject.toml requires-python
        3. Default to "3.11"

        Returns:
            Python version string (e.g., "3.11", "3.12")
        """
        if python_version_file:
            version = python_version_file.strip()
            # Extract major.minor (e.g., "3.11.5" -> "3.11")
            match = re.match(r'(\d+\.\d+)', version)
            if match:
                return match.group(1)

        if pyproject_content:
            match = re.search(r'requires-python\s*=\s*["\']>=?(\d+\.\d+)', pyproject_content)
            if match:
                return match.group(1)

        return "3.11"

    @staticmethod
    def _get_default_config(framework: str = "unknown", note: Optional[str] = None) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "framework": framework,
            "build_command": "npm run build",
            "install_command": "npm install",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "node_version": "18",
            "is_spa": True,
            "has_typescript": False,
            "package_manager": "npm",
            "scripts": {},
            "note": note,
            "confidence": "low"
        }

    @staticmethod
    def analyze_repository_structure(files: list, root_directory: str = "") -> Dict[str, Any]:
        """
        Analyze repository file structure to detect additional information.

        Args:
            files: List of file paths in the repository
            root_directory: Subdirectory path for monorepo support (e.g., "frontend")

        Returns:
            Dictionary with additional repository metadata
        """
        analysis = {
            "has_package_json": False,
            "has_typescript": False,
            "has_docker": False,
            "has_tests": False,
            "has_requirements_txt": False,
            "has_pyproject_toml": False,
            "has_pipfile": False,
            "has_setup_py": False,
            "lock_file": None,
            "config_files": []
        }

        # Normalize root_directory (remove leading/trailing slashes)
        root_dir = root_directory.strip("/") if root_directory else ""
        prefix = f"{root_dir}/" if root_dir else ""

        for file_path in files:
            # For monorepo support, only analyze files in the root_directory
            if root_dir and not file_path.startswith(prefix):
                continue

            # Strip the root_directory prefix for comparison
            relative_path = file_path[len(prefix):] if prefix else file_path
            file_lower = relative_path.lower()

            # Only check files directly in the root (not nested subdirectories)
            if "/" in relative_path:
                # Skip nested files except for tests
                if "test" in file_lower or "spec" in file_lower:
                    analysis["has_tests"] = True
                continue

            if relative_path == "package.json":
                analysis["has_package_json"] = True
            elif relative_path == "package-lock.json":
                analysis["lock_file"] = "npm"
            elif relative_path == "yarn.lock":
                analysis["lock_file"] = "yarn"
            elif relative_path == "pnpm-lock.yaml":
                analysis["lock_file"] = "pnpm"
            elif relative_path == "tsconfig.json":
                analysis["has_typescript"] = True
            elif relative_path in ["Dockerfile", "docker-compose.yml"]:
                analysis["has_docker"] = True
            elif relative_path == "requirements.txt":
                analysis["has_requirements_txt"] = True
            elif relative_path == "pyproject.toml":
                analysis["has_pyproject_toml"] = True
            elif relative_path == "Pipfile":
                analysis["has_pipfile"] = True
            elif relative_path in ["setup.py", "setup.cfg"]:
                analysis["has_setup_py"] = True
            elif relative_path in ["vite.config.js", "vite.config.ts", "next.config.js",
                               "vue.config.js", "angular.json", "gatsby-config.js"]:
                analysis["config_files"].append(relative_path)

        return analysis
