import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from celery_app import app, get_db
from app.models import Deployment
from app.services.cdn import CDNService
from app.config import get_settings

settings = get_settings()


@app.task(bind=True, name='tasks.cdn.purge_cdn_cache')
def purge_cdn_cache(self, deployment_id: int, wait_for_completion: bool = False):
    """
    Purge CDN cache for a deployment.

    Args:
        deployment_id: ID of the deployment
        wait_for_completion: Whether to wait for purge to complete

    Returns:
        dict with purge results
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get deployment and project
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return {'error': f'Deployment {deployment_id} not found'}

        project = deployment.project

        # Check if CDN is enabled
        if not settings.cdn_enabled or not settings.cdn_base_domain:
            # CDN not configured, skip purge
            return {
                'success': True,
                'message': 'CDN not configured, skipping cache purge',
                'skipped': True
            }

        # Generate subdomain for this project
        subdomain = f"{project.slug}.{settings.cdn_base_domain}"

        # Log callback
        def log_callback(message: str):
            """Append log message to deployment."""
            deployment.build_logs = (deployment.build_logs or "") + message + "\n"
            db.commit()

        log_callback("")
        log_callback("=" * 60)
        log_callback("CDN CACHE PURGE")
        log_callback("=" * 60)

        # Initialize CDN service
        cdn_service = CDNService()
        cdn_service.cdn_domain = subdomain

        # Purge cache for project (simple path: /projects/{slug}/)
        log_callback(f"Purging CDN cache for: projects/{project.slug}/")
        log_callback(f"CDN subdomain: {subdomain}")

        # Purge the entire project directory
        directory_url = f"https://{subdomain}/"

        purge_result = cdn_service.refresh_directory(directory_url)

        if not purge_result['success']:
            error_msg = purge_result.get('error', '')

            # Check for common CDN configuration errors
            if 'InvalidDomain.NotFound' in error_msg or 'does not belong to you' in error_msg:
                log_callback(f"⚠️  CDN domain '{settings.aliyun_cdn_domain}' is not configured in Alibaba Cloud CDN")
                log_callback(f"   To fix: Add '{settings.aliyun_cdn_domain}' to CDN console or remove ALIYUN_CDN_DOMAIN from .env")
                log_callback(f"   See CDN_SETUP_GUIDE.md for instructions")
            else:
                log_callback(f"⚠️  CDN cache purge failed: {error_msg}")

            # Return success=True to not block deployment
            return {
                'success': True,
                'warning': error_msg,
                'skipped': True
            }

        log_callback(f"✓ CDN cache purge initiated")
        log_callback(f"  Task ID: {purge_result.get('task_id')}")

        if wait_for_completion:
            if purge_result.get('completed'):
                log_callback(f"✓ CDN cache purge completed")
            else:
                log_callback(f"⚠️  CDN cache purge status: {purge_result.get('completion_status')}")

        log_callback("=" * 60)

        return purge_result

    except Exception as e:
        return {
            'success': False,
            'error': f'CDN purge failed: {str(e)}'
        }

    finally:
        if db:
            db.close()


@app.task(name='tasks.cdn.warm_deployment_cache')
def warm_deployment_cache(deployment_id: int, important_paths: list = None):
    """
    Warm up (pre-fetch) CDN cache for a deployment.

    Useful for ensuring fast first access to deployed sites.

    Args:
        deployment_id: ID of the deployment
        important_paths: List of important file paths to pre-fetch (e.g., ['index.html', 'main.js'])

    Returns:
        dict with warming results
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        # Get deployment and project
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return {'error': f'Deployment {deployment_id} not found'}

        project = deployment.project

        # Check if CDN is configured
        if not settings.aliyun_cdn_domain:
            return {
                'success': False,
                'error': 'CDN not configured'
            }

        # Initialize CDN service
        cdn_service = CDNService()

        # Default important paths
        if not important_paths:
            important_paths = [
                'index.html',
                'main.js',
                'index.js',
                'main.css',
                'index.css',
                'app.js',
                'bundle.js'
            ]

        # Construct full URLs
        base_url = f"https://{settings.aliyun_cdn_domain}/{project.user_id}/{project.id}/{deployment.commit_sha}"
        urls_to_warm = [
            f"{base_url}/{path}"
            for path in important_paths
        ]

        # Warm cache
        warm_result = cdn_service.push_object_cache(urls_to_warm)

        return warm_result

    except Exception as e:
        return {
            'success': False,
            'error': f'CDN warming failed: {str(e)}'
        }

    finally:
        if db:
            db.close()


@app.task(name='tasks.cdn.check_purge_status')
def check_purge_status(task_id: str):
    """
    Check status of a CDN purge task.

    Args:
        task_id: CDN purge task ID

    Returns:
        dict with task status
    """
    try:
        cdn_service = CDNService()

        result = cdn_service.describe_refresh_tasks(task_id=task_id)

        if not result['success']:
            return result

        tasks = result.get('tasks', [])
        if not tasks:
            return {
                'success': False,
                'error': f'Task {task_id} not found'
            }

        task = tasks[0]

        return {
            'success': True,
            'task_id': task_id,
            'status': task.get('Status'),
            'description': task.get('Description'),
            'process': task.get('Process'),
            'creation_time': task.get('CreationTime')
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to check purge status: {str(e)}'
        }
