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

        # Construct OSS path: user_id/project_id/commit_sha/
        oss_prefix = f"{project.user_id}/{project.id}/{deployment.commit_sha}/"

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

        # If CDN domain is configured, use CDN URL
        from app.config import get_settings
        settings = get_settings()

        if settings.aliyun_cdn_domain:
            # Replace OSS domain with CDN domain
            cdn_url = upload_result['index_url'].replace(
                f"{settings.aliyun_oss_bucket}.{settings.aliyun_oss_endpoint}",
                settings.aliyun_cdn_domain
            )
            deployment.cdn_url = cdn_url
            deployment.deployment_url = cdn_url  # Prefer CDN URL
            log_callback(f"CDN URL: {cdn_url}")

        # Mark as deployed
        deployment.status = DeploymentStatus.DEPLOYED
        deployment.deployed_at = datetime.utcnow()
        db.commit()

        log_callback("")
        log_callback("=" * 60)
        log_callback("DEPLOYMENT COMPLETED SUCCESSFULLY")
        log_callback("=" * 60)
        log_callback(f"Deployment URL: {deployment.deployment_url}")

        # Purge CDN cache if CDN is configured
        if settings.aliyun_cdn_domain:
            log_callback("")
            from .cdn import purge_cdn_cache

            # Trigger CDN cache purge asynchronously
            log_callback("Triggering CDN cache purge...")
            purge_result = purge_cdn_cache(deployment_id, wait_for_completion=False)

            if purge_result.get('success'):
                log_callback(f"✓ CDN cache purge initiated (Task ID: {purge_result.get('task_id')})")
            else:
                log_callback(f"⚠️  CDN cache purge failed: {purge_result.get('error', 'Unknown error')}")

        log_callback("")

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
def cleanup_old_deployments(project_id: int, keep_count: int = 10):
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
        from app.models import Project, Deployment

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

        deployments_to_delete = deployments[keep_count:]

        # Initialize OSS service
        oss_service = OSSService()

        deleted_count = 0
        for deployment in deployments_to_delete:
            # Delete from OSS
            oss_prefix = f"{project.user_id}/{project.id}/{deployment.commit_sha}/"
            try:
                files_deleted = oss_service.delete_directory(oss_prefix)
                deleted_count += 1
                print(f"Deleted deployment {deployment.id} from OSS ({files_deleted} files)")
            except Exception as e:
                print(f"Failed to delete deployment {deployment.id} from OSS: {e}")

            # Optionally delete deployment record from database
            # db.delete(deployment)

        db.commit()

        return {
            'success': True,
            'deployments_cleaned': deleted_count,
            'kept_count': keep_count
        }

    finally:
        if db:
            db.close()
