"""
Migration script: Explicit DNS records for static/frontend subdomains.

Currently, static project subdomains rely on a wildcard DNS record (*).
This script creates explicit ESA site DNS records + Aliyun DNS CNAMEs
for each existing static project, so the wildcard can be removed.

For each static project:
1. Create ESA site DNS record (CNAME, proxied, biz_name="web")
2. Look up the ESA-assigned record_cname
3. Create Aliyun DNS CNAME pointing subdomain → record_cname (upsert)
4. If staging_enabled, repeat for {slug}-staging subdomain
5. Also handle platform subdomain custom domains (e.g., docs.metavm.tech)

Run from the project root:
    PYTHONPATH=backend python scripts/migrate_frontend_dns.py [--dry-run]

Run staging first (with appropriate .env), then production.
Wildcard record removal is a manual step after verifying migration works.
"""

import sys
import argparse
import time

sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Project, CustomDomain
from app.services.esa import ESAService
from app.config import get_settings


def _migrate_subdomain(subdomain: str, esa_service: ESAService, dry_run: bool) -> str:
    """
    Migrate a single static subdomain. Returns status string.

    Possible return values: "created", "exists", "failed"
    """
    if dry_run:
        print(f"    [DRY RUN] Would create ESA record + DNS CNAME for {subdomain}")
        return "created"

    result = esa_service.setup_static_subdomain(subdomain)
    if result.get('success'):
        rc = result.get('record_cname', '(unknown)')
        print(f"    OK: {subdomain} → {rc}")
        return "created"
    elif result.get('already_exists'):
        print(f"    Already exists: {subdomain}")
        return "exists"
    else:
        error = result.get('error') or result.get('errors') or 'unknown error'
        print(f"    FAILED: {subdomain} — {error}")
        return "failed"


def main():
    parser = argparse.ArgumentParser(
        description="Create explicit ESA + DNS records for static project subdomains"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without making changes",
    )
    args = parser.parse_args()

    settings = get_settings()
    db = SessionLocal()
    esa_service = ESAService()

    try:
        projects = (
            db.query(Project)
            .filter(Project.project_type == "static")
            .order_by(Project.id)
            .all()
        )

        print(f"Environment: {settings.cdn_base_domain}")
        print(f"ESA site ID: {settings.aliyun_esa_site_id}")
        print(f"OSS origin: {esa_service.oss_origin}")
        print(f"Found {len(projects)} static project(s)")
        print(f"Dry run: {args.dry_run}\n")

        stats = {"created": 0, "exists": 0, "failed": 0}

        for project in projects:
            print(f"{'=' * 60}")
            print(f"Project #{project.id}: {project.slug}")
            print(f"{'=' * 60}")

            # --- Production subdomain ---
            subdomain = f"{project.slug}.{settings.cdn_base_domain}"
            print(f"  Production: {subdomain}")
            status = _migrate_subdomain(subdomain, esa_service, args.dry_run)
            stats[status] += 1

            # Brief pause to avoid API rate limits
            if not args.dry_run:
                time.sleep(1)

            # --- Staging subdomain ---
            if project.staging_enabled:
                staging_sub = f"{project.slug}-staging.{settings.cdn_base_domain}"
                print(f"  Staging: {staging_sub}")
                status = _migrate_subdomain(staging_sub, esa_service, args.dry_run)
                stats[status] += 1

                if not args.dry_run:
                    time.sleep(1)

            print()

        # --- Platform subdomain custom domains ---
        # Custom domains like docs.metavm.tech that are platform subdomains
        # pointing to static projects also need explicit ESA + DNS records.
        base = settings.cdn_base_domain
        custom_domains = (
            db.query(CustomDomain)
            .join(Project)
            .filter(
                CustomDomain.is_verified == True,
                Project.project_type == "static",
                CustomDomain.domain.like(f"%.{base}"),
            )
            .order_by(CustomDomain.id)
            .all()
        )

        # Filter to actual subdomains (exclude root domain which can't have CNAME)
        custom_subs = [
            cd for cd in custom_domains
            if cd.domain != base and cd.domain.endswith(f".{base}")
        ]

        if custom_subs:
            print(f"\n{'=' * 60}")
            print(f"Custom domain platform subdomains: {len(custom_subs)}")
            print(f"{'=' * 60}\n")

            for cd in custom_subs:
                # Skip if this subdomain matches a project slug (already handled above)
                slug_prefix = cd.domain.replace(f".{base}", "")
                is_project_slug = any(
                    slug_prefix == p.slug or slug_prefix == f"{p.slug}-staging"
                    for p in projects
                )
                if is_project_slug:
                    print(f"  {cd.domain} — skipped (matches project slug)")
                    continue

                print(f"  Custom domain: {cd.domain} → project {cd.project.slug}")
                status = _migrate_subdomain(cd.domain, esa_service, args.dry_run)
                stats[status] += 1

                if not args.dry_run:
                    time.sleep(1)

        print()
        print("=" * 60)
        print(f"Migration complete!")
        print(f"  Created: {stats['created']}")
        print(f"  Already existed: {stats['exists']}")
        print(f"  Failed: {stats['failed']}")
        print("=" * 60)

    finally:
        db.close()


if __name__ == '__main__':
    main()
