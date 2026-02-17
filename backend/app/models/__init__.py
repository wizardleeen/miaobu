from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from ..database import Base


class DeploymentStatus(str, enum.Enum):
    """Deployment status enumeration."""
    QUEUED = "queued"
    CLONING = "cloning"
    BUILDING = "building"
    UPLOADING = "uploading"
    DEPLOYED = "deployed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSLStatus(str, enum.Enum):
    """SSL certificate status enumeration."""
    PENDING = "pending"
    VERIFYING = "verifying"
    ISSUING = "issuing"
    ACTIVE = "active"
    FAILED = "failed"
    EXPIRED = "expired"


class User(Base):
    """User model for GitHub authenticated users."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(Integer, unique=True, nullable=False, index=True)
    github_username = Column(String(255), unique=True, nullable=False, index=True)
    github_email = Column(String(255))
    github_avatar_url = Column(String(512))
    github_access_token = Column(Text)  # Encrypted in production

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, github_username={self.github_username})>"


class Project(Base):
    """Project model for imported GitHub repositories."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Repository info
    github_repo_id = Column(Integer, nullable=False, index=True)
    github_repo_name = Column(String(255), nullable=False)  # owner/repo
    github_repo_url = Column(String(512), nullable=False)
    default_branch = Column(String(100), default="main", nullable=False)

    # Project settings
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)

    # Build configuration
    root_directory = Column(String(255), default="", nullable=False)  # Subdirectory for monorepo support
    build_command = Column(String(512), default="npm run build")
    install_command = Column(String(512), default="npm install")
    output_directory = Column(String(255), default="dist")
    node_version = Column(String(20), default="18")

    # Deployment info
    oss_path = Column(String(512))  # user_id/project_id/
    default_domain = Column(String(255))  # {slug}.miaobu.app

    # Webhook
    webhook_id = Column(Integer)
    webhook_secret = Column(String(255))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="projects")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan", order_by="Deployment.created_at.desc()")
    custom_domains = relationship("CustomDomain", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Project(id={self.id}, name={self.name}, slug={self.slug})>"


class Deployment(Base):
    """Deployment model for build and deploy jobs."""
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Git info
    commit_sha = Column(String(40), nullable=False, index=True)
    commit_message = Column(Text)
    commit_author = Column(String(255))
    branch = Column(String(100), nullable=False)

    # Build info
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.QUEUED, nullable=False, index=True)
    build_logs = Column(Text)
    error_message = Column(Text)

    # Deployment URLs
    oss_url = Column(String(512))
    cdn_url = Column(String(512))
    deployment_url = Column(String(512))  # Primary access URL

    # Metadata
    build_time_seconds = Column(Integer)
    celery_task_id = Column(String(255), index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deployed_at = Column(DateTime(timezone=True))

    # Relationships
    project = relationship("Project", back_populates="deployments")

    def __repr__(self):
        return f"<Deployment(id={self.id}, project_id={self.project_id}, status={self.status})>"


class CustomDomain(Base):
    """Custom domain model for user-configured domains."""
    __tablename__ = "custom_domains"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Domain info
    domain = Column(String(255), unique=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255))

    # SSL info (legacy - kept for backward compatibility)
    ssl_status = Column(SQLEnum(SSLStatus), default=SSLStatus.PENDING, nullable=False)
    ssl_certificate_id = Column(String(255))
    ssl_expires_at = Column(DateTime(timezone=True))

    # ESA (Edge Security Acceleration) fields
    esa_saas_id = Column(String(255), index=True)  # ESA SaaS manager ID
    esa_status = Column(String(50))  # ESA configuration status: pending, online, offline, error
    cname_target = Column(String(255), default="cname.metavm.tech")

    # Routing fields
    active_deployment_id = Column(Integer, ForeignKey("deployments.id"), index=True)  # Which deployment to serve
    edge_kv_synced = Column(Boolean, default=False, nullable=False)  # Whether Edge KV is up to date
    edge_kv_synced_at = Column(DateTime(timezone=True))  # Last successful KV sync time
    auto_update_enabled = Column(Boolean, default=False, nullable=False)  # Auto-promote new deployments

    # Domain type: 'cdn' (legacy) or 'esa' (new)
    domain_type = Column(String(20), default="esa", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True))

    # Relationships
    project = relationship("Project", back_populates="custom_domains")
    active_deployment = relationship(
        "Deployment",
        foreign_keys=[active_deployment_id],
        backref="custom_domains_using_this"
    )

    def __repr__(self):
        return f"<CustomDomain(id={self.id}, domain={self.domain}, is_verified={self.is_verified})>"


class BuildCache(Base):
    """Build cache model for storing dependency cache metadata."""
    __tablename__ = "build_cache"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    # Cache key (hash of package-lock.json or yarn.lock)
    cache_key = Column(String(64), nullable=False, index=True)

    # OSS path to cached node_modules
    oss_cache_path = Column(String(512), nullable=False)

    # Metadata
    size_bytes = Column(Integer)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<BuildCache(id={self.id}, project_id={self.project_id}, cache_key={self.cache_key})>"
