import os
from pathlib import Path

# Build directories
TEMP_DIR = Path("/tmp/miaobu-builds")
CACHE_DIR = Path("/build-cache")

# Ensure directories exist
TEMP_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Build configuration
BUILD_TIMEOUT = 3600  # 1 hour
CLONE_TIMEOUT = 300   # 5 minutes
INSTALL_TIMEOUT = 1800  # 30 minutes

# Docker configuration
DOCKER_NETWORK = "miaobu_default"
DOCKER_BUILD_IMAGE_PREFIX = "miaobu-build"

# Redis for log streaming
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
LOG_STREAM_PREFIX = "build:logs:"
LOG_EXPIRY = 3600  # 1 hour

# Database
DATABASE_URL = os.getenv('DATABASE_URL')
