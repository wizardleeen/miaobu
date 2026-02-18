#!/usr/bin/env python3
"""
Deploy Worker — polls PostgreSQL for DEPLOYING deployments and runs them.

Runs on the ECS server as a systemd service. Picks up deployments that the
build callback has marked as DEPLOYING and executes the actual deploy logic
(blue-green FC creation, Edge KV update, cache purge, etc.).

Single-process, single-deployment-at-a-time — no locking needed.
"""
import os
import sys
import time
import traceback

# Unset proxy env vars — the ECS host has a US proxy that breaks
# internal Aliyun API calls (OSS, FC, ESA)
for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(var, None)

# Load .env and fix host.docker.internal → localhost for bare-metal execution.
# The .env uses host.docker.internal for Docker containers, but the worker
# runs directly on the host.
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
with open(_env_path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.replace("host.docker.internal", "localhost")
        os.environ.setdefault(key.strip(), val.strip())

# Add backend to Python path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import SessionLocal  # noqa: E402
from app.models import Deployment, DeploymentStatus  # noqa: E402
from app.services.deploy import deploy_static, deploy_python, deploy_node, rollback_to_deployment  # noqa: E402

POLL_INTERVAL = 3  # seconds between polls when idle


def make_log(deployment, db):
    """Create a logging callback that appends to deployment.build_logs."""
    def log(msg):
        deployment.build_logs = (deployment.build_logs or "") + msg + "\n"
        db.commit()
    return log


def process_deployment(deployment, db):
    """Run the deploy for a single DEPLOYING deployment."""
    project = deployment.project
    log = make_log(deployment, db)

    # Rollback detection: if deployed_at is set, this deployment was previously
    # live and is being rolled back to (vs a fresh deploy from GHA).
    is_rollback = deployment.deployed_at is not None

    if is_rollback:
        log(f"[deploy-worker] Rollback to deployment #{deployment.id} "
            f"(project={project.slug}, type={project.project_type})")
        result = rollback_to_deployment(
            deployment_id=deployment.id,
            db=db,
            log=log,
        )
        # rollback_to_deployment() doesn't manage deployment status —
        # restore to DEPLOYED on success, set FAILED on failure
        if result.get("success"):
            deployment.status = DeploymentStatus.DEPLOYED
        else:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = result.get("error", "Rollback failed")
        db.commit()
    elif project.project_type == "python":
        oss_key = f"projects/{project.slug}/{deployment.id}/package.zip"
        log(f"[deploy-worker] Picked up deployment #{deployment.id} "
            f"(project={project.slug}, type={project.project_type})")
        result = deploy_python(
            deployment_id=deployment.id,
            oss_key=oss_key,
            db=db,
            log=log,
        )
    elif project.project_type == "node":
        oss_key = f"projects/{project.slug}/{deployment.id}/package.zip"
        log(f"[deploy-worker] Picked up deployment #{deployment.id} "
            f"(project={project.slug}, type={project.project_type})")
        result = deploy_node(
            deployment_id=deployment.id,
            oss_key=oss_key,
            db=db,
            log=log,
        )
    else:
        log(f"[deploy-worker] Picked up deployment #{deployment.id} "
            f"(project={project.slug}, type={project.project_type})")
        result = deploy_static(
            deployment_id=deployment.id,
            db=db,
            log=log,
        )

    if result.get("success"):
        log(f"[deploy-worker] Deployment #{deployment.id} succeeded")
    else:
        log(f"[deploy-worker] Deployment #{deployment.id} failed: {result.get('error')}")

    return result


def poll_once(db):
    """Check for one DEPLOYING deployment and process it. Returns True if work was done."""
    deployment = (
        db.query(Deployment)
        .filter(Deployment.status == DeploymentStatus.DEPLOYING)
        .order_by(Deployment.created_at.asc())
        .first()
    )

    if not deployment:
        return False

    print(f"[deploy-worker] Processing deployment #{deployment.id} "
          f"(project_id={deployment.project_id})")

    try:
        process_deployment(deployment, db)
    except Exception:
        # Unhandled exception — mark FAILED so it doesn't loop forever
        tb = traceback.format_exc()
        print(f"[deploy-worker] Unhandled error for deployment #{deployment.id}:\n{tb}")
        try:
            deployment.status = DeploymentStatus.FAILED
            deployment.error_message = f"Deploy worker error: {tb[-500:]}"
            deployment.build_logs = (deployment.build_logs or "") + f"\n[deploy-worker] FATAL: {tb}\n"
            db.commit()
        except Exception:
            # DB write failed too — rollback and move on
            db.rollback()
            print(f"[deploy-worker] Failed to mark deployment #{deployment.id} as FAILED")

    return True


def main():
    print("[deploy-worker] Starting deploy worker...")
    print(f"[deploy-worker] Poll interval: {POLL_INTERVAL}s")
    print(f"[deploy-worker] PID: {os.getpid()}")

    while True:
        db = SessionLocal()
        try:
            did_work = poll_once(db)
        except Exception:
            print(f"[deploy-worker] Poll error:\n{traceback.format_exc()}")
            did_work = False
        finally:
            db.close()

        if not did_work:
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
