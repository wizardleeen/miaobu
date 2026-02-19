"""Aggregate router for all public API sub-routers."""
from fastapi import APIRouter

from . import user, projects, deployments, domains, env_vars

router = APIRouter()

router.include_router(user.router)
router.include_router(projects.router)
router.include_router(deployments.router)
router.include_router(domains.router)
router.include_router(env_vars.router)
