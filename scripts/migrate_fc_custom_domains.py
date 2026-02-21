"""
Migration script: FC Custom Domains for Backend Apps

Migrates existing Python/Node.js projects from ESA Edge KV routing to
direct FC custom domains + DNS CNAME.

For each backend project with an active FC function:
1. Create DNS CNAME record pointing to FC account endpoint
2. Create FC custom domain for {slug}.{cdn_base_domain}
3. Optionally delete old Edge KV entry for the subdomain
4. Handle staging projects too (if staging_fc_function_name is set)

DNS must resolve before FC will accept the custom domain, so CNAME is
created first.  The CNAME target is the account-level FC endpoint
({account_id}.{fc_region}.fc.aliyuncs.com), not the per-function URL.

Run from the project root:
    cd /path/to/miaobu && PYTHONPATH=backend python scripts/migrate_fc_custom_domains.py

Pass --delete-kv to also remove old Edge KV entries for migrated subdomains.
"""

import sys
import argparse

sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Project
from app.services.fc import FCService
from app.services.alidns import AliDNSService
from app.services.esa import ESAService
from app.config import get_settings


def _migrate_subdomain(subdomain, function_name, fc_service, dns_service, esa_service, delete_kv):
    """Migrate a single subdomain: DNS CNAME first, then FC custom domain."""
    errors = 0
    fc_cname_target = fc_service.fc_cname_target

    # 1. DNS CNAME (must resolve before FC will accept the custom domain)
    dns_result = dns_service.add_cname_record(subdomain, fc_cname_target)
    if dns_result.get("success"):
        print(f"    DNS CNAME: OK ({subdomain} → {fc_cname_target})")
    else:
        print(f"    DNS CNAME: FAILED - {dns_result.get('error')}")
        errors += 1

    # 2. FC custom domain
    cd_result = fc_service.create_or_update_custom_domain(subdomain, function_name)
    if cd_result.get("success"):
        print(f"    FC custom domain: OK")
    else:
        print(f"    FC custom domain: FAILED - {cd_result.get('error')}")
        errors += 1

    # 3. Optionally delete Edge KV
    if delete_kv and esa_service:
        kv_result = esa_service.delete_edge_kv_mapping(subdomain)
        if kv_result.get("success"):
            print(f"    Edge KV deleted: OK")
        else:
            print(f"    Edge KV delete: FAILED - {kv_result.get('error')}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Migrate backend projects to FC custom domains")
    parser.add_argument("--delete-kv", action="store_true", help="Delete old Edge KV entries after migration")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes")
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    fc_service = FCService()
    dns_service = AliDNSService()
    esa_service = ESAService() if args.delete_kv else None

    try:
        projects = db.query(Project).filter(
            Project.project_type.in_(["python", "node"])
        ).all()

        print(f"Found {len(projects)} backend project(s) to migrate")
        print(f"Base domain: {settings.cdn_base_domain}")
        print(f"FC CNAME target: {fc_service.fc_cname_target}")
        print(f"Delete KV: {args.delete_kv}")
        print(f"Dry run: {args.dry_run}\n")

        migrated = 0
        errors = 0

        for project in projects:
            print(f"{'=' * 60}")
            print(f"Project #{project.id}: {project.slug} ({project.project_type})")
            print(f"{'=' * 60}")

            # --- Production ---
            if project.fc_function_name and project.fc_endpoint_url:
                subdomain = f"{project.slug}.{settings.cdn_base_domain}"

                print(f"  Production: {subdomain}")
                print(f"    FC function: {project.fc_function_name}")

                if not args.dry_run:
                    errors += _migrate_subdomain(
                        subdomain, project.fc_function_name,
                        fc_service, dns_service, esa_service, args.delete_kv,
                    )
                else:
                    print(f"    [DRY RUN] Would create DNS CNAME + FC custom domain")

                migrated += 1
            else:
                print(f"  Production: No FC function configured, skipping")

            # --- Staging ---
            if project.staging_enabled and project.staging_fc_function_name and getattr(project, 'staging_fc_endpoint_url', None):
                staging_subdomain = f"{project.slug}-staging.{settings.cdn_base_domain}"

                print(f"  Staging: {staging_subdomain}")
                print(f"    FC function: {project.staging_fc_function_name}")

                if not args.dry_run:
                    errors += _migrate_subdomain(
                        staging_subdomain, project.staging_fc_function_name,
                        fc_service, dns_service, esa_service, args.delete_kv,
                    )
                else:
                    print(f"    [DRY RUN] Would create DNS CNAME + FC custom domain")

            print()

        print("=" * 60)
        print(f"Migration complete! Migrated: {migrated}, Errors: {errors}")
        print("=" * 60)

    finally:
        db.close()


if __name__ == '__main__':
    main()
