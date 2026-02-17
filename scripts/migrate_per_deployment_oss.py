"""
Migration script: Per-Deployment OSS Paths

Migrates from shared `projects/{slug}/` to versioned `projects/{slug}/{deployment_id}/`.

What it does:
1. For each static project, copies OSS files from `projects/{slug}/` to
   `projects/{slug}/{latest_deployment_id}/`
2. Updates subdomain KV entries with the new oss_path
3. Updates custom domain KV entries and fixes active_deployment_id
   (old deployments' files were overwritten, so custom domains already
   served the latest version — this makes the pointer match reality)

Run inside the backend container:
    docker exec miaobu-backend python /app/../scripts/migrate_per_deployment_oss.py
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Project, Deployment, DeploymentStatus, CustomDomain
from app.services.oss import OSSService
from app.services.esa import ESAService
from app.config import get_settings

import oss2


def main():
    settings = get_settings()
    db = SessionLocal()
    oss_service = OSSService()
    esa_service = ESAService()

    # Get raw oss2 bucket for copy operations
    auth = oss2.Auth(settings.aliyun_access_key_id, settings.aliyun_access_key_secret)
    bucket = oss2.Bucket(auth, settings.aliyun_oss_endpoint, settings.aliyun_oss_bucket)

    try:
        projects = db.query(Project).filter(
            Project.project_type == "static"
        ).all()

        print(f"Found {len(projects)} static project(s) to migrate\n")

        for project in projects:
            print(f"{'=' * 60}")
            print(f"Project #{project.id}: {project.slug}")
            print(f"{'=' * 60}")

            # Find latest deployed deployment
            latest = db.query(Deployment).filter(
                Deployment.project_id == project.id,
                Deployment.status == DeploymentStatus.DEPLOYED
            ).order_by(Deployment.created_at.desc()).first()

            if not latest:
                print("  No deployed deployments, skipping\n")
                continue

            print(f"  Latest deployment: #{latest.id}")

            old_prefix = f"projects/{project.slug}/"
            new_prefix = f"projects/{project.slug}/{latest.id}/"

            # Check if already migrated (new path already has files)
            new_files = list(oss2.ObjectIterator(bucket, prefix=new_prefix, max_keys=1))
            if new_files:
                print(f"  New path {new_prefix} already has files — skipping OSS copy")
            else:
                # Copy files from old path to new path
                copied = 0
                for obj in oss2.ObjectIterator(bucket, prefix=old_prefix):
                    # Skip directory markers
                    if obj.key.endswith('/'):
                        continue
                    # Build new key: replace old_prefix with new_prefix
                    relative = obj.key[len(old_prefix):]

                    # Skip if it looks like a deployment-id subfolder (already versioned)
                    if relative.split('/')[0].isdigit():
                        continue

                    new_key = new_prefix + relative
                    bucket.copy_object(settings.aliyun_oss_bucket, obj.key, new_key)
                    copied += 1

                print(f"  Copied {copied} file(s): {old_prefix} -> {new_prefix}")

            # Update subdomain KV entry
            subdomain = f"{project.slug}.{settings.cdn_base_domain}"
            print(f"\n  Updating KV for subdomain: {subdomain}")

            kv_result = esa_service.get_edge_kv(subdomain)
            if kv_result.get('success') and kv_result.get('value'):
                try:
                    kv_data = json.loads(kv_result['value'])
                except (json.JSONDecodeError, TypeError):
                    kv_data = {}

                old_oss_path = kv_data.get('oss_path', '')
                new_oss_path = f"projects/{project.slug}/{latest.id}"
                kv_data['oss_path'] = new_oss_path
                kv_data['deployment_id'] = latest.id
                kv_data['updated_at'] = datetime.utcnow().isoformat()

                put_result = esa_service.put_edge_kv(subdomain, json.dumps(kv_data))
                if put_result.get('success'):
                    print(f"    OK: {old_oss_path} -> {new_oss_path}")
                else:
                    print(f"    FAILED: {put_result.get('error')}")
            else:
                print(f"    No existing KV entry, skipping")

            # Update custom domains
            custom_domains = db.query(CustomDomain).filter(
                CustomDomain.project_id == project.id,
                CustomDomain.is_verified == True,
            ).all()

            if custom_domains:
                print(f"\n  Updating {len(custom_domains)} custom domain(s):")

            for cd in custom_domains:
                old_dep_id = cd.active_deployment_id

                # Since files were always overwritten, the domain was actually
                # serving the latest deployment. Update pointer to match reality.
                if old_dep_id != latest.id:
                    cd.active_deployment_id = latest.id
                    print(f"    {cd.domain}: DB active_deployment_id {old_dep_id} -> {latest.id}")

                # Update KV
                kv_result = esa_service.get_edge_kv(cd.domain)
                if kv_result.get('success') and kv_result.get('value'):
                    try:
                        kv_data = json.loads(kv_result['value'])
                    except (json.JSONDecodeError, TypeError):
                        kv_data = {}

                    old_oss_path = kv_data.get('oss_path', '')
                    new_oss_path = f"projects/{project.slug}/{latest.id}"
                    kv_data['oss_path'] = new_oss_path
                    kv_data['deployment_id'] = latest.id
                    kv_data['updated_at'] = datetime.utcnow().isoformat()

                    put_result = esa_service.put_edge_kv(cd.domain, json.dumps(kv_data))
                    if put_result.get('success'):
                        print(f"    {cd.domain}: KV oss_path {old_oss_path} -> {new_oss_path}")
                    else:
                        print(f"    {cd.domain}: KV update FAILED: {put_result.get('error')}")
                else:
                    print(f"    {cd.domain}: No existing KV entry, skipping")

            db.commit()
            print()

        print("=" * 60)
        print("Migration complete!")
        print("=" * 60)

    finally:
        db.close()


if __name__ == '__main__':
    main()
