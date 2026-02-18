"""
Deploy Service — handles post-build deployment steps.

Called by the build callback endpoint after GitHub Actions uploads artifacts.
Extracted from worker/tasks/deploy.py and worker/tasks/build_python.py.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Deployment, DeploymentStatus, Project, CustomDomain,
    EnvironmentVariable, ProjectType,
)
from .esa import ESAService
from .oss import OSSService


def deploy_static(
    deployment_id: int,
    db: Session,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Finalize a static site deployment after OSS upload is done.

    Steps:
    1. Update Edge KV for subdomain routing
    2. Sync custom domains with auto-update enabled
    3. Purge ESA cache
    4. Mark deployment as DEPLOYED
    5. Schedule cleanup of old deployments

    Args:
        deployment_id: Deployment record ID
        db: Active SQLAlchemy session
        log: Optional logging callback
    """
    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project

    # Build the OSS path and deployment URL
    oss_prefix = f"projects/{project.slug}/{deployment_id}"
    subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    deployment_url = f"https://{subdomain}/"

    deployment.deployment_url = deployment_url
    deployment.cdn_url = deployment_url
    db.commit()

    # --- Edge KV for subdomain ---
    esa_service = ESAService()

    kv_value = json.dumps({
        "type": "static",
        "oss_path": oss_prefix,
        "is_spa": project.is_spa,
        "project_slug": project.slug,
        "deployment_id": deployment.id,
        "commit_sha": deployment.commit_sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    log("Updating Edge KV for subdomain routing...")
    kv_result = esa_service.put_edge_kv(subdomain, kv_value)
    if kv_result["success"]:
        log(f"Edge KV updated for {subdomain}")
    else:
        log(f"Warning: Edge KV update failed for {subdomain}: {kv_result.get('error')}")

    # --- Auto-update custom domains ---
    _sync_custom_domains_static(
        project=project,
        deployment=deployment,
        esa_service=esa_service,
        db=db,
        log=log,
    )

    # --- Mark DEPLOYED ---
    deployment.status = DeploymentStatus.DEPLOYED
    deployment.deployed_at = datetime.now(timezone.utc)
    db.commit()

    # --- Cache purge ---
    _purge_project_cache(project, esa_service, db, log)

    # --- Cleanup old deployments ---
    try:
        cleanup_old_deployments(project.id, db)
    except Exception as e:
        log(f"Warning: cleanup failed: {e}")

    log(f"Deployment URL: {deployment_url}")
    return {"success": True, "deployment_id": deployment_id, "deployment_url": deployment_url}


def deploy_python(
    deployment_id: int,
    oss_key: str,
    db: Session,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Finalize a Python project deployment using blue-green strategy.

    Creates a new FC function, health-checks it, then switches traffic.
    If the new function is unhealthy, the old one stays live.
    """
    from .fc import FCService

    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project
    start_command = project.start_command or "python -m uvicorn main:app --host 0.0.0.0 --port 9000"
    env_vars = _get_project_env_vars(project.id, db, log)

    def create_fc(fc_service: FCService, name: str) -> Dict[str, Any]:
        return fc_service.create_function(
            name=name,
            oss_bucket=settings.aliyun_fc_oss_bucket,
            oss_key=oss_key,
            start_command=start_command,
            python_version="3.10",
            env_vars=env_vars if env_vars else None,
        )

    return _deploy_fc_blue_green(
        deployment=deployment,
        project=project,
        db=db,
        log=log,
        kv_type="python",
        create_fc_fn=create_fc,
    )


def deploy_node(
    deployment_id: int,
    oss_key: str,
    db: Session,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Finalize a Node.js backend deployment using blue-green strategy.

    Creates a new FC function, health-checks it, then switches traffic.
    If the new function is unhealthy, the old one stays live.
    """
    from .fc import FCService

    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project
    start_command = project.start_command or "npm start"
    env_vars = _get_project_env_vars(project.id, db, log)

    def create_fc(fc_service: FCService, name: str) -> Dict[str, Any]:
        return fc_service.create_node_function(
            name=name,
            oss_bucket=settings.aliyun_fc_oss_bucket,
            oss_key=oss_key,
            start_command=start_command,
            env_vars=env_vars if env_vars else None,
        )

    return _deploy_fc_blue_green(
        deployment=deployment,
        project=project,
        db=db,
        log=log,
        kv_type="node",
        create_fc_fn=create_fc,
    )


def cleanup_old_deployments(
    project_id: int,
    db: Session,
    keep_count: int = 3,
) -> Dict[str, Any]:
    """
    Delete old deployment artifacts from OSS, mark records as PURGED.

    Keeps the most recent `keep_count` DEPLOYED deployments plus any
    pinned to custom domains via active_deployment_id.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": f"Project {project_id} not found"}

    deployments = (
        db.query(Deployment)
        .filter(
            Deployment.project_id == project_id,
            Deployment.status == DeploymentStatus.DEPLOYED,
        )
        .order_by(Deployment.created_at.desc())
        .all()
    )

    if len(deployments) <= keep_count:
        return {"message": f"Only {len(deployments)} deployments, nothing to clean up"}

    # Protect deployments pinned to custom domains
    protected_ids = set()
    active_domains = (
        db.query(CustomDomain)
        .filter(
            CustomDomain.project_id == project_id,
            CustomDomain.is_verified == True,
            CustomDomain.active_deployment_id.isnot(None),
        )
        .all()
    )
    for cd in active_domains:
        protected_ids.add(cd.active_deployment_id)

    to_delete = [d for d in deployments[keep_count:] if d.id not in protected_ids]

    oss_service = OSSService()
    deleted_count = 0

    for d in to_delete:
        oss_prefix = f"projects/{project.slug}/{d.id}/"
        try:
            oss_service.delete_directory(oss_prefix)
            d.status = DeploymentStatus.PURGED
            deleted_count += 1
        except Exception as e:
            print(f"Failed to delete deployment {d.id} from OSS: {e}")

    db.commit()
    return {
        "success": True,
        "deployments_cleaned": deleted_count,
        "deployments_protected": len(protected_ids),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deploy_fc_blue_green(
    deployment: Deployment,
    project: Project,
    db: Session,
    log: Callable,
    kv_type: str,
    create_fc_fn: Callable,
) -> Dict[str, Any]:
    """
    Blue-green deployment for FC-based projects (Python and Node.js).

    1. Create a NEW FC function with a unique per-deployment name
    2. Health-check the new function
    3. If healthy: switch Edge KV, update project, delete old function
    4. If unhealthy: delete broken function, keep old one live

    Args:
        deployment: Deployment record (already loaded)
        project: Project record
        db: Active SQLAlchemy session
        log: Logging callback
        kv_type: Edge KV type ("python" or "node")
        create_fc_fn: Callable(fc_service, name) -> fc result dict
    """
    from .fc import FCService

    settings = get_settings()

    deployment.status = DeploymentStatus.DEPLOYING
    db.commit()

    fc_service = FCService()
    new_name = f"miaobu-{project.slug}-d{deployment.id}"
    old_name = project.fc_function_name  # may be None on first deploy

    log(f"Creating new function: {new_name}")
    log(f"Previous function: {old_name or '(none)'}")

    # --- Create NEW FC function ---
    fc_result = create_fc_fn(fc_service, new_name)

    if not fc_result["success"]:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"FC function creation failed: {fc_result.get('error')}"
        db.commit()
        return {"success": False, "error": deployment.error_message}

    fc_endpoint = fc_result["endpoint_url"]
    deployment.fc_function_name = new_name
    db.commit()

    log(f"Function created: {new_name}")
    log(f"Endpoint: {fc_endpoint}")

    # --- Health check ---
    log("Running health check on new function...")
    health = fc_service.health_check(fc_endpoint)

    if not health["healthy"]:
        log(f"Health check FAILED: {health['error']}")
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"Health check failed: {health['error']}"
        db.commit()

        # Clean up the broken function (best-effort)
        log(f"Deleting broken function {new_name}...")
        try:
            fc_service.delete_function(new_name)
            log(f"Broken function {new_name} deleted")
        except Exception as e:
            log(f"Warning: failed to delete broken function {new_name}: {e}")

        return {"success": False, "error": deployment.error_message}

    log(f"Health check passed (status={health['status_code']}, "
        f"latency={health['latency_ms']}ms, attempt={health['attempt']})")

    # --- Switch traffic: update project and Edge KV ---
    project.fc_function_name = new_name
    project.fc_endpoint_url = fc_endpoint
    db.commit()

    commit_tag = deployment.commit_sha[:12] if deployment.commit_sha else "unknown"
    deployment.fc_function_version = commit_tag

    esa_service = ESAService()
    subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    deployment_url = f"https://{subdomain}/"

    kv_value = json.dumps({
        "type": kv_type,
        "fc_endpoint": fc_endpoint,
        "project_slug": project.slug,
        "deployment_id": deployment.id,
        "commit_sha": deployment.commit_sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    log("Updating Edge KV for subdomain routing...")
    kv_result = esa_service.put_edge_kv(subdomain, kv_value)
    if kv_result["success"]:
        log(f"Edge KV updated for {subdomain}")
    else:
        log(f"Warning: Edge KV update failed for {subdomain}: {kv_result.get('error')}")

    # --- Auto-update custom domains ---
    _sync_custom_domains_fc(
        project=project,
        deployment=deployment,
        fc_endpoint=fc_endpoint,
        esa_service=esa_service,
        db=db,
        log=log,
        kv_type=kv_type,
    )

    # --- Mark DEPLOYED ---
    deployment.status = DeploymentStatus.DEPLOYED
    deployment.deployed_at = datetime.now(timezone.utc)
    deployment.deployment_url = deployment_url
    db.commit()

    # --- Cache purge ---
    _purge_project_cache(project, esa_service, db, log)

    # --- Delete old function (best-effort) ---
    if old_name and old_name != new_name:
        log(f"Deleting old function {old_name}...")
        try:
            result = fc_service.delete_function(old_name)
            if result["success"]:
                log(f"Old function {old_name} deleted")
            else:
                log(f"Warning: failed to delete old function {old_name}: {result.get('error')}")
        except Exception as e:
            log(f"Warning: failed to delete old function {old_name}: {e}")

    log(f"Deployment URL: {deployment_url}")
    log(f"FC Endpoint: {fc_endpoint}")
    return {
        "success": True,
        "deployment_id": deployment.id,
        "deployment_url": deployment_url,
        "fc_endpoint": fc_endpoint,
    }


def _get_project_env_vars(
    project_id: int, db: Session, log: Callable
) -> Dict[str, str]:
    """Decrypt and return all environment variables for a project."""
    env_vars = {}
    try:
        from .encryption import decrypt_value

        records = (
            db.query(EnvironmentVariable)
            .filter(EnvironmentVariable.project_id == project_id)
            .all()
        )
        for rec in records:
            try:
                env_vars[rec.key] = decrypt_value(rec.value)
            except Exception:
                env_vars[rec.key] = rec.value
    except Exception as e:
        log(f"Warning: Could not load environment variables: {e}")
    return env_vars


def _sync_custom_domains_static(
    project: Project,
    deployment: Deployment,
    esa_service: ESAService,
    db: Session,
    log: Callable,
) -> None:
    """Update Edge KV for custom domains with auto-update enabled (static)."""
    try:
        domains = (
            db.query(CustomDomain)
            .filter(
                CustomDomain.project_id == project.id,
                CustomDomain.is_verified == True,
                CustomDomain.auto_update_enabled == True,
                CustomDomain.domain_type == "esa",
            )
            .all()
        )

        if not domains:
            return

        log(f"Updating {len(domains)} custom domain(s)...")
        for domain in domains:
            kv_result = esa_service.update_edge_kv_mapping(
                domain=domain.domain,
                user_id=project.user_id,
                project_id=project.id,
                deployment_id=deployment.id,
                commit_sha=deployment.commit_sha,
            )
            if kv_result["success"]:
                domain.active_deployment_id = deployment.id
                domain.edge_kv_synced = True
                domain.edge_kv_synced_at = datetime.now(timezone.utc)
                log(f"  {domain.domain} updated to deployment #{deployment.id}")
            else:
                domain.edge_kv_synced = False
                log(f"  Warning: {domain.domain} Edge KV update failed: {kv_result.get('error')}")

        db.commit()
    except Exception as e:
        log(f"Warning: custom domain sync failed: {e}")


def _sync_custom_domains_fc(
    project: Project,
    deployment: Deployment,
    fc_endpoint: str,
    esa_service: ESAService,
    db: Session,
    log: Callable,
    kv_type: str = "python",
) -> None:
    """Update Edge KV for custom domains with auto-update enabled (FC-based: Python or Node)."""
    try:
        domains = (
            db.query(CustomDomain)
            .filter(
                CustomDomain.project_id == project.id,
                CustomDomain.is_verified == True,
                CustomDomain.auto_update_enabled == True,
            )
            .all()
        )

        if not domains:
            return

        log(f"Updating {len(domains)} custom domain(s)...")
        for domain in domains:
            kv_value = json.dumps({
                "type": kv_type,
                "fc_endpoint": fc_endpoint,
                "project_slug": project.slug,
                "deployment_id": deployment.id,
                "commit_sha": deployment.commit_sha,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            kv_result = esa_service.put_edge_kv(domain.domain, kv_value)
            if kv_result["success"]:
                domain.active_deployment_id = deployment.id
                domain.edge_kv_synced = True
                domain.edge_kv_synced_at = datetime.now(timezone.utc)
                log(f"  {domain.domain} updated to deployment #{deployment.id}")
            else:
                domain.edge_kv_synced = False
                log(f"  Warning: {domain.domain} Edge KV update failed: {kv_result.get('error')}")

        db.commit()
    except Exception as e:
        log(f"Warning: custom domain sync failed: {e}")


def _purge_project_cache(
    project: Project,
    esa_service: ESAService,
    db: Session,
    log: Callable,
) -> None:
    """Purge ESA cache for subdomain + all verified custom domains."""
    settings = get_settings()
    try:
        hostnames = [f"{project.slug}.{settings.cdn_base_domain}"]
        verified = (
            db.query(CustomDomain)
            .filter(
                CustomDomain.project_id == project.id,
                CustomDomain.is_verified == True,
            )
            .all()
        )
        for cd in verified:
            hostnames.append(cd.domain)

        result = esa_service.purge_host_cache(hostnames)
        if result.get("success"):
            log(f"ESA cache purged for {', '.join(hostnames)}")
        else:
            log(f"Warning: ESA cache purge failed: {result.get('error')}")
    except Exception as e:
        log(f"Warning: ESA cache purge failed: {e}")
