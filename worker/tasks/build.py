from celery import chain
from datetime import datetime
import sys
from pathlib import Path

# Add backend to path for database imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from celery_app import app, get_db
from app.models import Deployment, Project, DeploymentStatus
from builders.docker_builder import DockerBuilder


@app.task(bind=True, name='tasks.build.build_and_deploy')
def build_and_deploy(self, deployment_id: int):
    """
    Main orchestration task for building and deploying a project.

    Args:
        deployment_id: ID of the deployment record

    Returns:
        dict with deployment status and output path
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

        # Update status to building
        deployment.status = DeploymentStatus.CLONING
        deployment.celery_task_id = self.request.id
        deployment.build_logs = ""
        db.commit()

        # Initialize builder
        builder = DockerBuilder(deployment_id)

        # Set up log callback to update database
        def log_callback(message: str):
            """Append log message to deployment."""
            deployment.build_logs = (deployment.build_logs or "") + message + "\n"
            db.commit()

        builder.set_log_callback(log_callback)

        try:
            # Step 1: Clone repository
            builder.log("=" * 60)
            builder.log("STEP 1: CLONING REPOSITORY")
            builder.log("=" * 60)

            # Get user's GitHub token from project owner
            user = project.user
            repo_dir = builder.clone_repository(
                repo_url=project.github_repo_url,
                branch=deployment.branch,
                commit_sha=deployment.commit_sha,
                access_token=user.github_access_token
            )

            # Step 2: Install dependencies
            deployment.status = DeploymentStatus.BUILDING
            db.commit()

            builder.log("")
            builder.log("=" * 60)
            builder.log("STEP 2: INSTALLING DEPENDENCIES")
            builder.log("=" * 60)

            builder.install_dependencies(
                repo_dir=repo_dir,
                install_command=project.install_command,
                node_version=project.node_version,
                use_cache=True,
                root_directory=project.root_directory or ""
            )

            # Step 3: Run build
            builder.log("")
            builder.log("=" * 60)
            builder.log("STEP 3: RUNNING BUILD")
            builder.log("=" * 60)

            built_dir = builder.run_build(
                repo_dir=repo_dir,
                build_command=project.build_command,
                node_version=project.node_version,
                root_directory=project.root_directory or ""
            )

            # Step 4: Verify output directory exists
            # For monorepo, output is relative to root_directory
            if project.root_directory:
                base_dir = built_dir / project.root_directory
            else:
                base_dir = built_dir
            output_dir = base_dir / project.output_directory
            if not output_dir.exists():
                raise Exception(
                    f"Build output directory '{project.output_directory}' not found. "
                    f"Available directories: {[d.name for d in base_dir.iterdir() if d.is_dir()]}"
                )

            builder.log("")
            builder.log("=" * 60)
            builder.log("STEP 4: BUILD VERIFICATION")
            builder.log("=" * 60)
            builder.log(f"✓ Output directory found: {output_dir}")

            # List output files
            output_files = list(output_dir.rglob('*'))
            builder.log(f"✓ Build produced {len(output_files)} files")

            # Update deployment status
            deployment.status = DeploymentStatus.UPLOADING
            db.commit()

            builder.log("")
            builder.log("=" * 60)
            builder.log("BUILD COMPLETED SUCCESSFULLY")
            builder.log("=" * 60)

            # Step 5: Upload to OSS
            from .deploy import upload_to_oss

            # Call upload task directly (synchronous within this task)
            upload_result = upload_to_oss(deployment_id, str(output_dir))

            if not upload_result.get('success'):
                raise Exception(f"OSS upload failed: {upload_result.get('error', 'Unknown error')}")

            return {
                'success': True,
                'deployment_id': deployment_id,
                'output_dir': str(output_dir),
                'file_count': len(output_files),
                'oss_url': upload_result.get('oss_url'),
                'cdn_url': upload_result.get('cdn_url'),
                'deployment_url': upload_result.get('deployment_url')
            }

        except Exception as e:
            # Update deployment status to failed
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            db.commit()

            builder.log(f"Build failed: {str(e)}", "ERROR")
            raise

        finally:
            # Cleanup
            builder.cleanup()
            db.close()

    except Exception as e:
        if db:
            db.close()
        raise


@app.task(name='tasks.build.cancel_deployment')
def cancel_deployment(deployment_id: int):
    """
    Cancel a running deployment.

    Args:
        deployment_id: ID of the deployment to cancel
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return {'error': f'Deployment {deployment_id} not found'}

        # Revoke Celery task if it has one
        if deployment.celery_task_id:
            app.control.revoke(deployment.celery_task_id, terminate=True)

        # Update status
        deployment.status = DeploymentStatus.CANCELLED
        db.commit()

        return {'success': True, 'deployment_id': deployment_id}

    finally:
        if db:
            db.close()


@app.task(name='tasks.build.get_build_logs')
def get_build_logs(deployment_id: int):
    """
    Get build logs from Redis stream.

    Args:
        deployment_id: ID of the deployment

    Returns:
        List of log lines
    """
    import redis
    from config import REDIS_URL, LOG_STREAM_PREFIX

    redis_client = redis.from_url(REDIS_URL)
    log_key = f"{LOG_STREAM_PREFIX}{deployment_id}"

    # Get logs from Redis
    logs = redis_client.lrange(log_key, 0, -1)
    return [log.decode('utf-8') for log in logs]
