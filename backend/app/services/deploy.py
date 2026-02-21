"""
Deploy Service — handles post-build deployment steps.

Called by the build callback endpoint after GitHub Actions uploads artifacts.
Uses in-place FC updates (zero-downtime ~300ms) instead of blue-green.
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
    is_staging = deployment.is_staging

    # Build the OSS path and deployment URL
    oss_prefix = f"projects/{project.slug}/{deployment_id}"
    if is_staging:
        subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"
    else:
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    deployment_url = f"https://{subdomain}/"

    deployment.deployment_url = deployment_url
    deployment.cdn_url = deployment_url
    db.commit()

    # --- Edge KV for subdomain ---
    esa_service = ESAService()

    kv_data = {
        "type": "static",
        "oss_path": oss_prefix,
        "is_spa": project.is_spa,
        "project_slug": project.slug,
        "deployment_id": deployment.id,
        "commit_sha": deployment.commit_sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if is_staging:
        kv_data["staging"] = True
        if project.staging_password:
            kv_data["staging_password_hash"] = project.staging_password
    kv_value = json.dumps(kv_data)

    log("Updating Edge KV for subdomain routing...")
    kv_result = esa_service.put_edge_kv(subdomain, kv_value)
    if kv_result["success"]:
        log(f"Edge KV updated for {subdomain}")
    else:
        log(f"Warning: Edge KV update failed for {subdomain}: {kv_result.get('error')}")

    # --- Auto-update custom domains (production only) ---
    if not is_staging:
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
    if is_staging:
        project.staging_deployment_id = deployment.id
    else:
        project.active_deployment_id = deployment.id
    db.commit()

    # --- Cache purge ---
    _purge_hostnames([subdomain], esa_service, log)

    # --- Cleanup old deployments ---
    try:
        cleanup_old_deployments(project.id, db, is_staging=is_staging)
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
    Finalize a Python project deployment using in-place FC update.

    Uses a stable function name (miaobu-{slug}) and updates it in place.
    FC UpdateFunction provides zero-downtime updates (~300ms).
    """
    from .fc import FCService

    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project
    is_staging = deployment.is_staging
    start_command = project.start_command or "python -m uvicorn main:app --host 0.0.0.0 --port 9000"
    env_scope = "staging" if is_staging else "production"
    env_vars = _get_project_env_vars(project.id, db, log, environment=env_scope)

    deployment.status = DeploymentStatus.DEPLOYING
    db.commit()

    fc_service = FCService()
    if is_staging:
        stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}-staging"
        old_name = project.staging_fc_function_name
    else:
        stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}"
        old_name = project.fc_function_name  # may differ if migrating from blue-green

    log(f"Deploying function: {stable_name}")

    fc_result = fc_service.create_or_update_function(
        name=stable_name,
        oss_bucket=settings.aliyun_fc_oss_bucket,
        oss_key=oss_key,
        start_command=start_command,
        python_version="3.10",
        env_vars=env_vars if env_vars else None,
    )

    if not fc_result["success"]:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"FC function deploy failed: {fc_result.get('error')}"
        db.commit()
        return {"success": False, "error": deployment.error_message}

    fc_endpoint = fc_result["endpoint_url"]

    # Update project to track the stable function
    if is_staging:
        project.staging_fc_function_name = stable_name
        project.staging_fc_endpoint_url = fc_endpoint
    else:
        project.fc_function_name = stable_name
        project.fc_endpoint_url = fc_endpoint
    db.commit()

    # --- Subdomain setup ---
    if is_staging:
        subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"
    else:
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    deployment_url = f"https://{subdomain}/"

    commit_tag = deployment.commit_sha[:12] if deployment.commit_sha else "unknown"
    deployment.fc_function_version = commit_tag

    # --- FC custom domain + DNS (direct routing, bypasses ESA) ---
    _setup_fc_direct_domain(subdomain, stable_name, fc_endpoint, fc_service, log)

    # --- Auto-update custom domains via ESA (external domains only) ---
    if not is_staging:
        esa_service = ESAService()
        _sync_custom_domains_fc(
            project=project,
            deployment=deployment,
            fc_endpoint=fc_endpoint,
            esa_service=esa_service,
            db=db,
            log=log,
            kv_type="python",
        )

    # --- Mark DEPLOYED ---
    deployment.status = DeploymentStatus.DEPLOYED
    deployment.deployed_at = datetime.now(timezone.utc)
    deployment.deployment_url = deployment_url
    if is_staging:
        project.staging_deployment_id = deployment.id
    else:
        project.active_deployment_id = deployment.id
    db.commit()

    # --- Migrate from old blue-green function name ---
    if old_name and old_name != stable_name:
        log(f"Cleaning up old function {old_name}...")
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


def deploy_node(
    deployment_id: int,
    oss_key: str,
    db: Session,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Finalize a Node.js backend deployment using in-place FC update.

    Uses a stable function name (miaobu-{slug}) and updates it in place.
    FC UpdateFunction provides zero-downtime updates (~300ms).
    """
    from .fc import FCService

    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project
    is_staging = deployment.is_staging
    start_command = project.start_command or "npm start"
    env_scope = "staging" if is_staging else "production"
    env_vars = _get_project_env_vars(project.id, db, log, environment=env_scope)

    deployment.status = DeploymentStatus.DEPLOYING
    db.commit()

    fc_service = FCService()
    if is_staging:
        stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}-staging"
        old_name = project.staging_fc_function_name
    else:
        stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}"
        old_name = project.fc_function_name  # may differ if migrating from blue-green

    log(f"Deploying function: {stable_name}")

    fc_result = fc_service.create_or_update_node_function(
        name=stable_name,
        oss_bucket=settings.aliyun_fc_oss_bucket,
        oss_key=oss_key,
        start_command=start_command,
        env_vars=env_vars if env_vars else None,
    )

    if not fc_result["success"]:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"FC function deploy failed: {fc_result.get('error')}"
        db.commit()
        return {"success": False, "error": deployment.error_message}

    fc_endpoint = fc_result["endpoint_url"]

    # Update project to track the stable function
    if is_staging:
        project.staging_fc_function_name = stable_name
        project.staging_fc_endpoint_url = fc_endpoint
    else:
        project.fc_function_name = stable_name
        project.fc_endpoint_url = fc_endpoint
    db.commit()

    # --- Subdomain setup ---
    if is_staging:
        subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"
    else:
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    deployment_url = f"https://{subdomain}/"

    commit_tag = deployment.commit_sha[:12] if deployment.commit_sha else "unknown"
    deployment.fc_function_version = commit_tag

    # --- FC custom domain + DNS (direct routing, bypasses ESA) ---
    _setup_fc_direct_domain(subdomain, stable_name, fc_endpoint, fc_service, log)

    # --- Auto-update custom domains via ESA (external domains only) ---
    if not is_staging:
        esa_service = ESAService()
        _sync_custom_domains_fc(
            project=project,
            deployment=deployment,
            fc_endpoint=fc_endpoint,
            esa_service=esa_service,
            db=db,
            log=log,
            kv_type="node",
        )

    # --- Mark DEPLOYED ---
    deployment.status = DeploymentStatus.DEPLOYED
    deployment.deployed_at = datetime.now(timezone.utc)
    deployment.deployment_url = deployment_url
    if is_staging:
        project.staging_deployment_id = deployment.id
    else:
        project.active_deployment_id = deployment.id
    db.commit()

    # --- Migrate from old blue-green function name ---
    if old_name and old_name != stable_name:
        log(f"Cleaning up old function {old_name}...")
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


def cleanup_old_deployments(
    project_id: int,
    db: Session,
    keep_count: int = 3,
    is_staging: bool = False,
) -> Dict[str, Any]:
    """
    Delete old deployment artifacts from OSS, mark records as PURGED.

    Keeps the most recent `keep_count` DEPLOYED deployments plus any
    pinned to custom domains via active_deployment_id or as the
    project's active/staging deployment.
    """
    settings = get_settings()
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": f"Project {project_id} not found"}

    deployments = (
        db.query(Deployment)
        .filter(
            Deployment.project_id == project_id,
            Deployment.status == DeploymentStatus.DEPLOYED,
            Deployment.is_staging == is_staging,
        )
        .order_by(Deployment.created_at.desc())
        .all()
    )

    if len(deployments) <= keep_count:
        return {"message": f"Only {len(deployments)} deployments, nothing to clean up"}

    # Protect deployments pinned to custom domains
    protected_ids = set()
    if not is_staging:
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

    # Protect the project's active/staging deployment
    if is_staging:
        if project.staging_deployment_id:
            protected_ids.add(project.staging_deployment_id)
    else:
        if project.active_deployment_id:
            protected_ids.add(project.active_deployment_id)

    to_delete = [d for d in deployments[keep_count:] if d.id not in protected_ids]

    is_fc = project.project_type in ("python", "node")
    oss_service = OSSService()
    fc_oss_service = None
    if is_fc:
        fc_oss_service = OSSService(
            bucket_name=settings.aliyun_fc_oss_bucket,
            endpoint=settings.aliyun_fc_oss_endpoint,
        )

    deleted_count = 0

    for d in to_delete:
        try:
            if is_fc and fc_oss_service:
                # Delete FC package from Qingdao bucket
                fc_oss_service.delete_directory(f"projects/{project.slug}/{d.id}/")
            else:
                # Delete static files from Hangzhou bucket
                oss_service.delete_directory(f"projects/{project.slug}/{d.id}/")
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


def rollback_to_deployment(
    deployment_id: int,
    db: Session,
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Roll back a project to serve an older deployment.

    For static sites: updates Edge KV to point to the old oss_path.
    For FC projects: updates the stable function with the old package.

    Args:
        deployment_id: The target deployment to roll back to
        db: Active SQLAlchemy session
        log: Optional logging callback
    """
    from .fc import FCService

    settings = get_settings()
    if log is None:
        log = lambda msg: None

    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return {"success": False, "error": f"Deployment {deployment_id} not found"}

    project = deployment.project
    is_staging = deployment.is_staging

    if is_staging:
        subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"
    else:
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
    esa_service = ESAService()

    if project.project_type == "static":
        # --- Static rollback: just switch Edge KV ---
        oss_prefix = f"projects/{project.slug}/{deployment.id}"

        kv_data = {
            "type": "static",
            "oss_path": oss_prefix,
            "is_spa": project.is_spa,
            "project_slug": project.slug,
            "deployment_id": deployment.id,
            "commit_sha": deployment.commit_sha,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if is_staging:
            kv_data["staging"] = True
            if project.staging_password:
                kv_data["staging_password_hash"] = project.staging_password
        kv_value = json.dumps(kv_data)

        log(f"Rolling back to deployment #{deployment.id}...")
        kv_result = esa_service.put_edge_kv(subdomain, kv_value)
        if not kv_result["success"]:
            return {"success": False, "error": f"Edge KV update failed: {kv_result.get('error')}"}

        log(f"Edge KV updated for {subdomain}")

        # Sync auto-update custom domains (production only)
        if not is_staging:
            _sync_custom_domains_static(
                project=project,
                deployment=deployment,
                esa_service=esa_service,
                db=db,
                log=log,
            )

    else:
        # --- FC rollback: update stable function with old package ---
        oss_key = f"projects/{project.slug}/{deployment.id}/package.zip"

        # Verify the package still exists
        fc_oss_service = OSSService(
            bucket_name=settings.aliyun_fc_oss_bucket,
            endpoint=settings.aliyun_fc_oss_endpoint,
        )
        if not fc_oss_service.object_exists(oss_key):
            return {"success": False, "error": "Deployment package no longer exists in storage"}

        log(f"Rolling back to deployment #{deployment.id} (FC {project.project_type})...")

        fc_service = FCService()
        if is_staging:
            stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}-staging"
        else:
            stable_name = f"{settings.miaobu_fc_prefix}-{project.slug}"
        start_command = project.start_command or (
            "python -m uvicorn main:app --host 0.0.0.0 --port 9000"
            if project.project_type == "python"
            else "npm start"
        )
        env_scope = "staging" if is_staging else "production"
        env_vars = _get_project_env_vars(project.id, db, log, environment=env_scope)

        log(f"Updating function: {stable_name}")
        if project.project_type == "python":
            fc_result = fc_service.create_or_update_function(
                name=stable_name,
                oss_bucket=settings.aliyun_fc_oss_bucket,
                oss_key=oss_key,
                start_command=start_command,
                python_version="3.10",
                env_vars=env_vars if env_vars else None,
            )
        else:
            fc_result = fc_service.create_or_update_node_function(
                name=stable_name,
                oss_bucket=settings.aliyun_fc_oss_bucket,
                oss_key=oss_key,
                start_command=start_command,
                env_vars=env_vars if env_vars else None,
            )

        if not fc_result["success"]:
            return {"success": False, "error": f"FC function update failed: {fc_result.get('error')}"}

        fc_endpoint = fc_result["endpoint_url"]

        # Update project
        if is_staging:
            project.staging_fc_function_name = stable_name
            project.staging_fc_endpoint_url = fc_endpoint
        else:
            project.fc_function_name = stable_name
            project.fc_endpoint_url = fc_endpoint
        db.commit()

        # FC custom domain + DNS (direct routing, bypasses ESA)
        _setup_fc_direct_domain(subdomain, stable_name, fc_endpoint, fc_service, log)

        # Sync auto-update custom domains via ESA (external domains only)
        if not is_staging:
            _sync_custom_domains_fc(
                project=project,
                deployment=deployment,
                fc_endpoint=fc_endpoint,
                esa_service=esa_service,
                db=db,
                log=log,
                kv_type=project.project_type,
            )

    # --- Update project active/staging deployment ---
    if is_staging:
        project.staging_deployment_id = deployment.id
    else:
        project.active_deployment_id = deployment.id
    db.commit()

    deployment_url = f"https://{subdomain}/"
    log(f"Rollback complete. Deployment URL: {deployment_url}")
    return {"success": True, "deployment_id": deployment.id, "deployment_url": deployment_url}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_fc_direct_domain(
    subdomain: str,
    function_name: str,
    fc_endpoint: str,
    fc_service,
    log: Callable,
) -> None:
    """
    Create DNS CNAME + FC custom domain so that *subdomain* routes directly
    to the FC function, bypassing ESA.

    Order matters: FC validates that the CNAME already resolves to its
    endpoint **before** accepting the custom domain, so DNS must be first.
    The CNAME target is the account-level FC endpoint
    (``{account_id}.{fc_region}.fc.aliyuncs.com``), not the per-function URL.
    """
    from .alidns import AliDNSService

    # 1. DNS CNAME → FC account endpoint (must resolve before step 2)
    fc_cname_target = fc_service.fc_cname_target
    dns_service = AliDNSService()
    dns_result = dns_service.add_cname_record(subdomain, fc_cname_target)
    if dns_result.get("success"):
        log(f"DNS CNAME set: {subdomain} → {fc_cname_target}")
    else:
        log(f"Warning: DNS CNAME failed: {dns_result.get('error')}")

    # 2. FC custom domain (route + TLS cert)
    cd_result = fc_service.create_or_update_custom_domain(subdomain, function_name)
    if cd_result.get("success"):
        log(f"FC custom domain configured: {subdomain}")
    else:
        log(f"Warning: FC custom domain failed: {cd_result.get('error')}")


def _get_project_env_vars(
    project_id: int, db: Session, log: Callable, environment: str = "production"
) -> Dict[str, str]:
    """Decrypt and return environment variables for a project, scoped by environment."""
    env_vars = {}
    try:
        from .encryption import decrypt_value

        records = (
            db.query(EnvironmentVariable)
            .filter(
                EnvironmentVariable.project_id == project_id,
                EnvironmentVariable.environment == environment,
            )
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


def _purge_hostnames(
    hostnames: list,
    esa_service: ESAService,
    log: Callable,
) -> None:
    """Purge ESA cache for a list of hostnames."""
    try:
        result = esa_service.purge_host_cache(hostnames)
        if result.get("success"):
            log(f"ESA cache purged for {', '.join(hostnames)}")
        else:
            log(f"Warning: ESA cache purge failed: {result.get('error')}")
    except Exception as e:
        log(f"Warning: ESA cache purge failed: {e}")


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
