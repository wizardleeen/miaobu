import json
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from celery_app import app, get_db
from app.models import Deployment, DeploymentStatus
from app.services.oss import OSSService


@app.task(bind=True, name='tasks.deploy.upload_to_oss')
def upload_to_oss(self, deployment_id: int, build_output_dir: str):
    """
    Upload build artifacts to Alibaba Cloud OSS.

    Args:
        deployment_id: ID of the deployment record
        build_output_dir: Path to the build output directory

    Returns:
        dict with upload results and URLs
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get deployment and project from database
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return {'error': f'Deployment {deployment_id} not found'}

        project = deployment.project

        # Get settings
        from app.config import get_settings
        settings = get_settings()

        # Initialize OSS service
        oss_service = OSSService()

        # Set up log callback to update deployment
        def log_callback(message: str):
            """Append log message to deployment."""
            deployment.build_logs = (deployment.build_logs or "") + message + "\n"
            db.commit()

        log_callback("")
        log_callback("=" * 60)
        log_callback("STEP 5: UPLOADING TO OSS")
        log_callback("=" * 60)

        # Path: /projects/{slug}/{deployment_id}/
        # Each deployment gets its own path for multi-version support
        oss_prefix = f"projects/{project.slug}/{deployment_id}/"

        log_callback(f"OSS path: {oss_prefix}")
        log_callback(f"Subdomain: {project.slug}.{settings.cdn_base_domain}")

        # Upload directory to OSS
        build_dir = Path(build_output_dir)
        if not build_dir.exists():
            raise Exception(f"Build output directory not found: {build_output_dir}")

        upload_result = oss_service.upload_directory(
            local_dir=build_dir,
            oss_prefix=oss_prefix,
            log_callback=log_callback
        )

        # Update deployment with OSS URLs
        deployment.oss_url = upload_result['index_url']
        deployment.deployment_url = upload_result['index_url']

        # Generate deployment URL using subdomain
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"
        deployment_url = f"https://{subdomain}/"
        deployment.cdn_url = deployment_url
        deployment.deployment_url = deployment_url
        log_callback(f"✓ Deployment URL: {deployment_url}")
        log_callback(f"✓ Access your site at: https://{subdomain}")

        # Mark as deployed
        deployment.status = DeploymentStatus.DEPLOYED
        deployment.deployed_at = datetime.utcnow()
        db.commit()

        # Write subdomain KV entry for ESA Edge Routine routing
        try:
            from app.services.esa import ESAService

            esa_service = ESAService()
            subdomain_key = f"{project.slug}.{settings.cdn_base_domain}"
            kv_value = json.dumps({
                "type": "static",
                "oss_path": oss_prefix.rstrip('/'),
                "is_spa": project.is_spa,
                "project_slug": project.slug,
                "deployment_id": deployment.id,
                "commit_sha": deployment.commit_sha,
                "updated_at": datetime.utcnow().isoformat(),
            })

            log_callback("")
            log_callback("Updating ESA Edge KV for subdomain routing...")
            kv_result = esa_service.put_edge_kv(subdomain_key, kv_value)
            if kv_result['success']:
                log_callback(f"✓ Edge KV updated for {subdomain_key}")
            else:
                log_callback(f"⚠️  Edge KV update failed for {subdomain_key}: {kv_result.get('error')}")
        except Exception as e:
            log_callback(f"⚠️  Subdomain KV update failed: {str(e)}")

        # Auto-update custom domains with auto_update_enabled (ESA)
        try:
            from app.models import CustomDomain

            log_callback("")
            log_callback("Checking for custom domains with auto-update...")

            # Find custom domains with auto-update enabled for this project
            auto_update_domains = db.query(CustomDomain).filter(
                CustomDomain.project_id == project.id,
                CustomDomain.is_verified == True,
                CustomDomain.auto_update_enabled == True,
                CustomDomain.domain_type == "esa"
            ).all()

            if auto_update_domains:
                log_callback(f"Found {len(auto_update_domains)} domain(s) with auto-update enabled")
                if 'esa_service' not in locals():
                    esa_service = ESAService()

                for domain in auto_update_domains:
                    log_callback(f"  Updating {domain.domain}...")

                    # Update Edge KV mapping
                    kv_result = esa_service.update_edge_kv_mapping(
                        domain=domain.domain,
                        user_id=project.user_id,
                        project_id=project.id,
                        deployment_id=deployment.id,
                        commit_sha=deployment.commit_sha
                    )

                    if kv_result['success']:
                        # Update database
                        domain.active_deployment_id = deployment.id
                        domain.edge_kv_synced = True
                        domain.edge_kv_synced_at = datetime.utcnow()
                        log_callback(f"  ✓ {domain.domain} updated to deployment #{deployment.id}")
                    else:
                        domain.edge_kv_synced = False
                        log_callback(f"  ⚠️  {domain.domain} Edge KV update failed: {kv_result.get('error')}")

                db.commit()
            else:
                log_callback("No domains with auto-update enabled")

        except Exception as e:
            log_callback(f"⚠️  Auto-update check failed: {str(e)}")
            # Don't fail the deployment if auto-update fails

        log_callback("")
        log_callback("=" * 60)
        log_callback("DEPLOYMENT COMPLETED SUCCESSFULLY")
        log_callback("=" * 60)
        log_callback(f"Deployment URL: {deployment.deployment_url}")

        # Purge ESA cache for the subdomain and all verified custom domains
        try:
            log_callback("")
            log_callback("Purging ESA cache...")
            if 'esa_service' not in locals():
                from app.services.esa import ESAService
                esa_service = ESAService()

            # Collect all hostnames to purge
            hostnames_to_purge = [f"{project.slug}.{settings.cdn_base_domain}"]

            from app.models import CustomDomain as CD
            all_verified_domains = db.query(CD).filter(
                CD.project_id == project.id,
                CD.is_verified == True,
            ).all()
            for cd in all_verified_domains:
                hostnames_to_purge.append(cd.domain)

            purge_result = esa_service.purge_host_cache(hostnames_to_purge)

            if purge_result.get('success'):
                log_callback(f"✓ ESA cache purged for {', '.join(hostnames_to_purge)}")
            else:
                log_callback(f"⚠️  ESA cache purge failed: {purge_result.get('error', 'Unknown error')}")
        except Exception as e:
            log_callback(f"⚠️  ESA cache purge failed: {str(e)}")

        log_callback("")

        # Trigger cleanup of old deployments in the background
        try:
            cleanup_old_deployments.delay(project.id)
        except Exception as e:
            log_callback(f"⚠️  Failed to schedule cleanup: {str(e)}")

        return {
            'success': True,
            'deployment_id': deployment_id,
            'files_uploaded': upload_result['files_uploaded'],
            'total_size': upload_result['total_size'],
            'oss_url': upload_result['index_url'],
            'cdn_url': deployment.cdn_url,
            'deployment_url': deployment.deployment_url
        }

    except Exception as e:
        # Update deployment status to failed
        if 'deployment' in locals() and deployment:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = f"OSS upload failed: {str(e)}"
            deployment.build_logs = (deployment.build_logs or "") + f"\n[ERROR] OSS upload failed: {str(e)}\n"
            db.commit()

        raise

    finally:
        if db:
            db.close()


@app.task(name='tasks.deploy.cleanup_old_deployments')
def cleanup_old_deployments(project_id: int, keep_count: int = 3):
    """
    Cleanup old deployments for a project.

    Keeps only the most recent N deployments, deletes older ones from OSS.

    Args:
        project_id: ID of the project
        keep_count: Number of recent deployments to keep (default: 10)
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        from app.models import Project, Deployment, CustomDomain

        # Get project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {'error': f'Project {project_id} not found'}

        # Get all deployed deployments, sorted by creation date (newest first)
        deployments = db.query(Deployment).filter(
            Deployment.project_id == project_id,
            Deployment.status == DeploymentStatus.DEPLOYED
        ).order_by(Deployment.created_at.desc()).all()

        # Keep only the most recent N
        if len(deployments) <= keep_count:
            return {'message': f'Only {len(deployments)} deployments, nothing to clean up'}

        # Collect deployment IDs that are actively serving custom domains
        protected_ids = set()
        active_domains = db.query(CustomDomain).filter(
            CustomDomain.project_id == project_id,
            CustomDomain.is_verified == True,
            CustomDomain.active_deployment_id.isnot(None),
        ).all()
        for cd in active_domains:
            protected_ids.add(cd.active_deployment_id)

        deployments_to_delete = [
            d for d in deployments[keep_count:]
            if d.id not in protected_ids
        ]

        # Initialize OSS service
        oss_service = OSSService()

        deleted_count = 0
        for deployment in deployments_to_delete:
            # Delete from OSS using per-deployment path
            oss_prefix = f"projects/{project.slug}/{deployment.id}/"
            try:
                files_deleted = oss_service.delete_directory(oss_prefix)
                deployment.status = DeploymentStatus.PURGED
                deleted_count += 1
                print(f"Deleted deployment {deployment.id} from OSS ({files_deleted} files)")
            except Exception as e:
                print(f"Failed to delete deployment {deployment.id} from OSS: {e}")

        db.commit()

        return {
            'success': True,
            'deployments_cleaned': deleted_count,
            'deployments_protected': len(protected_ids),
            'kept_count': keep_count
        }

    finally:
        if db:
            db.close()
