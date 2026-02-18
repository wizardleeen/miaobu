import subprocess
import sys
import json
import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

# Add backend to path for database imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'backend'))

from celery_app import app, get_db
from app.models import Deployment, Project, DeploymentStatus
from app.config import get_settings
from builders.docker_builder import DockerBuilder

settings = get_settings()


@app.task(bind=True, name='tasks.build_python.build_and_deploy_python')
def build_and_deploy_python(self, deployment_id: int):
    """
    Build and deploy a Python project to Function Compute.

    Steps:
    1. Clone repository
    2. Install Python dependencies (via Docker for compatibility)
    3. Create code package (zip)
    4. Upload to OSS
    5. Deploy to FC (code package mode)
    6. Update Edge KV mappings
    7. Mark as deployed

    Args:
        deployment_id: ID of the deployment record
    """
    db = get_db()
    if not db:
        return {'error': 'Database not available'}

    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return {'error': f'Deployment {deployment_id} not found'}

        project = deployment.project
        start_time = datetime.utcnow()

        # Update status
        deployment.status = DeploymentStatus.CLONING
        deployment.celery_task_id = self.request.id
        deployment.build_logs = ""
        db.commit()

        # Initialize builder for cloning
        builder = DockerBuilder(deployment_id)

        def log(message: str):
            deployment.build_logs = (deployment.build_logs or "") + message + "\n"
            db.commit()

        builder.set_log_callback(log)

        try:
            # Step 1: Clone repository
            log("=" * 60)
            log("STEP 1: CLONING REPOSITORY")
            log("=" * 60)

            user = project.user
            repo_dir = builder.clone_repository(
                repo_url=project.github_repo_url,
                branch=deployment.branch,
                commit_sha=deployment.commit_sha,
                access_token=user.github_access_token,
            )

            # Handle root_directory for monorepo
            work_dir = repo_dir
            if project.root_directory:
                work_dir = repo_dir / project.root_directory
                if not work_dir.exists():
                    raise Exception(f"Root directory '{project.root_directory}' not found in repository")

            # Step 2: Install dependencies
            deployment.status = DeploymentStatus.BUILDING
            db.commit()

            log("")
            log("=" * 60)
            log("STEP 2: INSTALLING DEPENDENCIES")
            log("=" * 60)

            # MUST match the FC layer's Python version (python310/versions/1)
            # Ignore project.python_version — FC runtime is always 3.10
            python_version = "3.10"
            has_requirements = (work_dir / "requirements.txt").exists()
            has_pyproject = (work_dir / "pyproject.toml").exists()
            has_pipfile = (work_dir / "Pipfile").exists()

            deps_dir = work_dir / "python_deps"
            deps_dir.mkdir(exist_ok=True)

            if has_requirements:
                log(f"Installing from requirements.txt (Python {python_version})")
                result = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "-v", f"{work_dir}:/app",
                        f"python:{python_version}-slim",
                        "pip", "install", "--no-cache-dir",
                        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
                        "-r", "/app/requirements.txt",
                        "--target", "/app/python_deps",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )

                if result.returncode != 0:
                    log(f"pip output:\n{result.stdout[-2000:]}")
                    log(f"pip errors:\n{result.stderr[-2000:]}")
                    raise Exception(f"pip install failed: {result.stderr[-500:]}")

                log(f"Dependencies installed successfully")
            elif has_pyproject:
                log(f"Installing from pyproject.toml (Python {python_version})")
                result = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "-v", f"{work_dir}:/app",
                        "-w", "/app",
                        f"python:{python_version}-slim",
                        "pip", "install", "--no-cache-dir",
                        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
                        ".", "--target", "/app/python_deps",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )

                if result.returncode != 0:
                    log(f"pip errors:\n{result.stderr[-2000:]}")
                    raise Exception(f"pip install failed: {result.stderr[-500:]}")

                log(f"Dependencies installed successfully")
            else:
                log("No requirements.txt or pyproject.toml found, skipping dependency install")

            # Step 3: Create code package (zip)
            log("")
            log("=" * 60)
            log("STEP 3: CREATING CODE PACKAGE")
            log("=" * 60)

            deployment.status = DeploymentStatus.UPLOADING
            db.commit()

            commit_tag = deployment.commit_sha[:12]
            zip_filename = f"{project.slug}-{commit_tag}.zip"
            zip_path = Path(f"/tmp/miaobu-builds/{zip_filename}")
            zip_path.parent.mkdir(parents=True, exist_ok=True)

            # Create zip with all code + dependencies
            with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in work_dir.rglob('*'):
                    if file_path.is_file():
                        # Skip git directory and other unnecessary files
                        rel_path = file_path.relative_to(work_dir)
                        rel_str = str(rel_path)
                        if rel_str.startswith('.git/') or rel_str.startswith('__pycache__/'):
                            continue
                        zf.write(file_path, rel_path)

            zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
            log(f"Code package created: {zip_filename} ({zip_size_mb:.1f} MB)")

            if zip_size_mb > 500:
                raise Exception(f"Code package too large ({zip_size_mb:.1f} MB > 500 MB limit)")

            # Step 4: Upload to OSS
            log("")
            log("=" * 60)
            log("STEP 4: UPLOADING TO OSS")
            log("=" * 60)

            import oss2

            auth = oss2.Auth(settings.aliyun_access_key_id, settings.aliyun_access_key_secret)
            # Use Qingdao OSS with internal endpoint for fast uploads (co-located with server)
            fc_oss_bucket = settings.aliyun_fc_oss_bucket
            bucket = oss2.Bucket(auth, 'oss-cn-qingdao-internal.aliyuncs.com', fc_oss_bucket)

            oss_key = f"fc-packages/{project.slug}/{commit_tag}.zip"
            bucket.put_object_from_file(oss_key, str(zip_path))

            log(f"Uploaded to OSS: {oss_key}")

            # Clean up local zip
            zip_path.unlink(missing_ok=True)

            # Step 5: Deploy to Function Compute
            log("")
            log("=" * 60)
            log("STEP 5: DEPLOYING TO FUNCTION COMPUTE")
            log("=" * 60)

            deployment.status = DeploymentStatus.DEPLOYING
            db.commit()

            from app.services.fc import FCService

            fc_service = FCService()
            fc_function_name = f"miaobu-{project.slug}"
            start_command = project.start_command or "python -m uvicorn main:app --host 0.0.0.0 --port 9000"

            # Collect environment variables
            env_vars = {}
            try:
                from app.models import EnvironmentVariable
                from app.services.encryption import decrypt_value

                env_records = db.query(EnvironmentVariable).filter(
                    EnvironmentVariable.project_id == project.id
                ).all()

                for env_record in env_records:
                    try:
                        env_vars[env_record.key] = decrypt_value(env_record.value)
                    except Exception:
                        env_vars[env_record.key] = env_record.value
            except Exception as e:
                log(f"Warning: Could not load environment variables: {e}")

            log(f"Function name: {fc_function_name}")
            log(f"Start command: {start_command}")

            fc_result = fc_service.create_or_update_function(
                name=fc_function_name,
                oss_bucket=fc_oss_bucket,
                oss_key=oss_key,
                start_command=start_command,
                python_version=python_version,
                env_vars=env_vars if env_vars else None,
            )

            if not fc_result['success']:
                raise Exception(f"FC deployment failed: {fc_result.get('error')}")

            fc_endpoint = fc_result['endpoint_url']
            log(f"Function deployed: {fc_function_name}")
            log(f"Endpoint: {fc_endpoint}")

            # Update project with FC info
            project.fc_function_name = fc_function_name
            project.fc_endpoint_url = fc_endpoint
            db.commit()

            # Update deployment with FC info
            deployment.fc_function_version = commit_tag

            # Step 6: Update Edge KV mappings
            log("")
            log("=" * 60)
            log("STEP 6: UPDATING EDGE ROUTING")
            log("=" * 60)

            try:
                from app.services.esa import ESAService
                esa_service = ESAService()

                # Update subdomain KV entry for Python project
                subdomain = f"{project.slug}.{settings.cdn_base_domain}"
                kv_value = json.dumps({
                    "type": "python",
                    "fc_endpoint": fc_endpoint,
                    "project_slug": project.slug,
                    "deployment_id": deployment.id,
                    "commit_sha": deployment.commit_sha,
                    "updated_at": datetime.utcnow().isoformat(),
                })

                kv_result = esa_service.put_edge_kv(subdomain, kv_value)
                if kv_result['success']:
                    log(f"Edge KV updated for {subdomain}")
                else:
                    log(f"Warning: Edge KV update failed for {subdomain}: {kv_result.get('error')}")

                # Update custom domains with auto-update
                from app.models import CustomDomain

                auto_update_domains = db.query(CustomDomain).filter(
                    CustomDomain.project_id == project.id,
                    CustomDomain.is_verified == True,
                    CustomDomain.auto_update_enabled == True,
                ).all()

                for domain in auto_update_domains:
                    domain_kv_value = json.dumps({
                        "type": "python",
                        "fc_endpoint": fc_endpoint,
                        "project_slug": project.slug,
                        "deployment_id": deployment.id,
                        "commit_sha": deployment.commit_sha,
                        "updated_at": datetime.utcnow().isoformat(),
                    })
                    domain_result = esa_service.put_edge_kv(domain.domain, domain_kv_value)
                    if domain_result['success']:
                        domain.active_deployment_id = deployment.id
                        domain.edge_kv_synced = True
                        domain.edge_kv_synced_at = datetime.utcnow()
                        log(f"Edge KV updated for custom domain {domain.domain}")
                    else:
                        log(f"Warning: Edge KV update failed for {domain.domain}")

                db.commit()

            except Exception as e:
                log(f"Warning: Edge KV update failed: {e}")

            # Step 7: Mark as deployed
            log("")
            log("=" * 60)
            log("DEPLOYMENT COMPLETED SUCCESSFULLY")
            log("=" * 60)

            end_time = datetime.utcnow()
            build_seconds = int((end_time - start_time).total_seconds())

            deployment.status = DeploymentStatus.DEPLOYED
            deployment.deployed_at = end_time
            deployment.build_time_seconds = build_seconds
            deployment.deployment_url = f"https://{project.slug}.{settings.cdn_base_domain}/"
            db.commit()

            # Purge ESA cache for subdomain and custom domains
            try:
                from app.models import CustomDomain as CD
                hostnames_to_purge = [f"{project.slug}.{settings.cdn_base_domain}"]
                all_verified = db.query(CD).filter(
                    CD.project_id == project.id,
                    CD.is_verified == True,
                ).all()
                for cd in all_verified:
                    hostnames_to_purge.append(cd.domain)
                purge_result = esa_service.purge_host_cache(hostnames_to_purge)
                if purge_result.get('success'):
                    log(f"ESA cache purged for {', '.join(hostnames_to_purge)}")
                else:
                    log(f"Warning: ESA cache purge failed: {purge_result.get('error')}")
            except Exception as e:
                log(f"Warning: ESA cache purge failed: {e}")

            log(f"Build time: {build_seconds}s")
            log(f"Deployment URL: {deployment.deployment_url}")
            log(f"FC Endpoint: {fc_endpoint}")

            return {
                'success': True,
                'deployment_id': deployment_id,
                'fc_endpoint': fc_endpoint,
                'deployment_url': deployment.deployment_url,
            }

        except Exception as e:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = str(e)
            end_time = datetime.utcnow()
            deployment.build_time_seconds = int((end_time - start_time).total_seconds())
            db.commit()

            log(f"[ERROR] Build failed: {str(e)}")
            raise

        finally:
            builder.cleanup()
            db.close()

    except Exception as e:
        if db:
            db.close()
        raise
