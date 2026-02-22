from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, HttpUrl
from datetime import datetime
from typing import Optional, List
from enum import Enum


# Enums matching models
class ProjectType(str, Enum):
    STATIC = "static"
    PYTHON = "python"
    NODE = "node"
    MANUL = "manul"


class DeploymentStatus(str, Enum):
    QUEUED = "queued"
    CLONING = "cloning"
    BUILDING = "building"
    UPLOADING = "uploading"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    PURGED = "purged"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSLStatus(str, Enum):
    PENDING = "pending"
    VERIFYING = "verifying"
    ISSUING = "issuing"
    ACTIVE = "active"
    FAILED = "failed"
    EXPIRED = "expired"


# User Schemas
class UserBase(BaseModel):
    github_username: str
    github_email: Optional[str] = None
    github_avatar_url: Optional[str] = None


class UserCreate(UserBase):
    github_id: int
    github_access_token: str


class UserResponse(UserBase):
    id: int
    github_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Project Schemas
class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    project_type: str = Field(default="static")
    root_directory: str = Field(default="", max_length=255, description="Subdirectory for monorepo support (e.g., 'frontend')")
    build_command: str = Field(default="npm run build", max_length=512)
    install_command: str = Field(default="npm install", max_length=512)
    output_directory: str = Field(default="dist", max_length=255)
    is_spa: bool = Field(default=True)
    node_version: str = Field(default="18", max_length=20)
    python_version: Optional[str] = Field(None, max_length=20)
    start_command: Optional[str] = Field(None, max_length=512)
    python_framework: Optional[str] = Field(None, max_length=50)


class ProjectCreate(ProjectBase):
    github_repo_id: int
    github_repo_name: str
    github_repo_url: str
    default_branch: str = "main"


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    project_type: Optional[str] = None
    root_directory: Optional[str] = Field(None, max_length=255, description="Subdirectory for monorepo support (e.g., 'frontend')")
    build_command: Optional[str] = Field(None, max_length=512)
    install_command: Optional[str] = Field(None, max_length=512)
    output_directory: Optional[str] = Field(None, max_length=255)
    is_spa: Optional[bool] = None
    node_version: Optional[str] = Field(None, max_length=20)
    python_version: Optional[str] = Field(None, max_length=20)
    start_command: Optional[str] = Field(None, max_length=512)
    python_framework: Optional[str] = Field(None, max_length=50)
    staging_enabled: Optional[bool] = None
    staging_password: Optional[str] = Field(None, max_length=255)


class ProjectResponse(ProjectBase):
    id: int
    user_id: int
    github_repo_id: int
    github_repo_name: str
    github_repo_url: str
    default_branch: str
    slug: str
    oss_path: Optional[str] = None
    default_domain: Optional[str] = None
    webhook_id: Optional[int] = None
    fc_function_name: Optional[str] = None
    fc_endpoint_url: Optional[str] = None
    manul_app_id: Optional[int] = None
    manul_app_name: Optional[str] = None
    active_deployment_id: Optional[int] = None
    staging_enabled: bool = False
    staging_deployment_id: Optional[int] = None
    staging_domain: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectWithDeployments(ProjectResponse):
    deployments: List[DeploymentResponse] = []


# Deployment Schemas
class DeploymentBase(BaseModel):
    commit_sha: str = Field(..., max_length=100)  # Allow "manual" or full git SHA
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    branch: str = Field(..., max_length=100)


class DeploymentCreate(DeploymentBase):
    project_id: int


class DeploymentResponse(DeploymentBase):
    id: int
    project_id: int
    status: DeploymentStatus
    is_staging: bool = False
    build_logs: Optional[str] = None
    error_message: Optional[str] = None
    oss_url: Optional[str] = None
    cdn_url: Optional[str] = None
    deployment_url: Optional[str] = None
    fc_function_name: Optional[str] = None
    fc_function_version: Optional[str] = None
    fc_image_uri: Optional[str] = None
    build_time_seconds: Optional[int] = None
    celery_task_id: Optional[str] = None  # Legacy — kept for old deployment records
    created_at: datetime
    updated_at: datetime
    deployed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Custom Domain Schemas
class CustomDomainBase(BaseModel):
    domain: str = Field(..., min_length=3, max_length=255)


class CustomDomainCreate(CustomDomainBase):
    project_id: int


class CustomDomainResponse(CustomDomainBase):
    id: int
    project_id: int
    is_verified: bool
    verification_token: Optional[str] = None
    ssl_status: SSLStatus
    ssl_certificate_id: Optional[str] = None
    ssl_expires_at: Optional[datetime] = None

    # ESA fields
    esa_saas_id: Optional[str] = None
    esa_status: Optional[str] = None
    cname_target: Optional[str] = None
    active_deployment_id: Optional[int] = None
    edge_kv_synced: bool = False
    edge_kv_synced_at: Optional[datetime] = None
    auto_update_enabled: bool = False
    domain_type: str = "esa"

    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Environment Variable Schemas
class EnvironmentVariableBase(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(...)
    is_secret: bool = Field(default=False)


class EnvironmentVariableCreate(EnvironmentVariableBase):
    environment: str = Field(default="production")


class EnvironmentVariableUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=255)
    value: Optional[str] = None
    is_secret: Optional[bool] = None


class EnvironmentVariableResponse(BaseModel):
    id: int
    project_id: int
    key: str
    value: str  # Masked for secrets
    is_secret: bool
    environment: str = "production"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None


class GitHubUser(BaseModel):
    id: int
    login: str
    email: Optional[str] = None
    avatar_url: str
    name: Optional[str] = None


# Webhook Schemas
class WebhookPayload(BaseModel):
    ref: str
    after: str
    repository: dict
    head_commit: Optional[dict] = None
    pusher: Optional[dict] = None


# Health Check
class HealthCheck(BaseModel):
    status: str = "ok"
    timestamp: datetime


# API Token Schemas
class ApiTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class ApiTokenResponse(BaseModel):
    id: int
    name: str
    prefix: str
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApiTokenCreated(ApiTokenResponse):
    token: str  # Full token, shown only once


# Rebuild models to resolve forward references
ProjectWithDeployments.model_rebuild()
