import json
from typing import Dict, Optional, Any
import re


class BuildDetector:
    """Service for detecting build configuration from repository files."""

    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "astro": {
            "indicators": ["astro"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run dev"
        },
        "vite": {
            "indicators": ["vite", "@vitejs/plugin-react"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run dev"
        },
        "create-react-app": {
            "indicators": ["react-scripts"],
            "build_command": "npm run build",
            "output_directory": "build",
            "dev_command": "npm start"
        },
        "next": {
            "indicators": ["next"],
            "build_command": "npm run build && npm run export",
            "output_directory": "out",
            "dev_command": "npm run dev",
            "note": "Requires static export configuration"
        },
        "vue-cli": {
            "indicators": ["@vue/cli-service"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "npm run serve"
        },
        "nuxt": {
            "indicators": ["nuxt"],
            "build_command": "npm run generate",
            "output_directory": "dist",
            "dev_command": "npm run dev"
        },
        "gatsby": {
            "indicators": ["gatsby"],
            "build_command": "npm run build",
            "output_directory": "public",
            "dev_command": "npm run develop"
        },
        "angular": {
            "indicators": ["@angular/cli"],
            "build_command": "npm run build",
            "output_directory": "dist",
            "dev_command": "ng serve"
        },
        "svelte": {
            "indicators": ["svelte"],
            "build_command": "npm run build",
            "output_directory": "public/build",
            "dev_command": "npm run dev"
        },
        "docusaurus": {
            "indicators": ["@docusaurus/core"],
            "build_command": "npm run build",
            "output_directory": "build",
            "dev_command": "npm run start"
        },
        "vuepress": {
            "indicators": ["vuepress"],
            "build_command": "npm run build",
            "output_directory": "docs/.vuepress/dist",
            "dev_command": "npm run dev"
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
        else:
            # Try to infer from scripts
            build_command = scripts.get("build", "npm run build")
            output_directory = BuildDetector._guess_output_directory(build_command, all_deps)
            dev_command = scripts.get("dev") or scripts.get("start", "npm start")
            note = None

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
            "has_typescript": "typescript" in all_deps,
            "package_manager": BuildDetector._detect_package_manager(package_data),
            "scripts": scripts,
            "note": note,
            "confidence": "high" if detected_framework else "medium"
        }

    @staticmethod
    def _detect_node_version(package_data: Dict) -> str:
        """Detect required Node.js version from package.json."""
        engines = package_data.get("engines", {})
        node_version = engines.get("node", "")

        if node_version:
            # Extract version number (e.g., ">=16.0.0" -> "16", "^18.0.0" -> "18")
            match = re.search(r"(\d+)", node_version)
            if match:
                version = match.group(1)
                # Map to supported versions
                version_num = int(version)
                if version_num >= 20:
                    return "20"
                elif version_num >= 18:
                    return "18"
                elif version_num >= 16:
                    return "16"

        # Default to 18 (LTS)
        return "18"

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
    def _get_default_config(framework: str = "unknown", note: Optional[str] = None) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "framework": framework,
            "build_command": "npm run build",
            "install_command": "npm install",
            "output_directory": "dist",
            "dev_command": "npm run dev",
            "node_version": "18",
            "has_typescript": False,
            "package_manager": "npm",
            "scripts": {},
            "note": note,
            "confidence": "low"
        }

    @staticmethod
    def analyze_repository_structure(files: list) -> Dict[str, Any]:
        """
        Analyze repository file structure to detect additional information.

        Args:
            files: List of file paths in the repository

        Returns:
            Dictionary with additional repository metadata
        """
        analysis = {
            "has_package_json": False,
            "has_typescript": False,
            "has_docker": False,
            "has_tests": False,
            "lock_file": None,
            "config_files": []
        }

        for file_path in files:
            file_lower = file_path.lower()

            if file_path == "package.json":
                analysis["has_package_json"] = True
            elif file_path == "package-lock.json":
                analysis["lock_file"] = "npm"
            elif file_path == "yarn.lock":
                analysis["lock_file"] = "yarn"
            elif file_path == "pnpm-lock.yaml":
                analysis["lock_file"] = "pnpm"
            elif file_path == "tsconfig.json":
                analysis["has_typescript"] = True
            elif file_path in ["Dockerfile", "docker-compose.yml"]:
                analysis["has_docker"] = True
            elif "test" in file_lower or "spec" in file_lower:
                analysis["has_tests"] = True
            elif file_path in ["vite.config.js", "vite.config.ts", "next.config.js",
                               "vue.config.js", "angular.json", "gatsby-config.js"]:
                analysis["config_files"].append(file_path)

        return analysis
