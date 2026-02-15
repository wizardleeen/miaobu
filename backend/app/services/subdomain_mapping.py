"""
Service to manage subdomain to OSS path mappings for EdgeScript.

Generates a JSON file that EdgeScript can use to route requests (optional).
"""
import json
from typing import Dict
from sqlalchemy.orm import Session
from ..models import Project, Deployment, DeploymentStatus
from .oss import OSSService


class SubdomainMappingService:
    """
    Manages the subdomain-to-path mapping file in OSS.

    EdgeScript can read this file to know which OSS path to fetch
    for each subdomain (optional - direct mapping also works).
    """

    def __init__(self):
        self.oss_service = OSSService()
        self.mapping_file = "_miaobu/subdomain-map.json"

    def generate_mapping(self, db: Session) -> Dict[str, dict]:
        """
        Generate complete subdomain mapping from database.

        NEW SIMPLIFIED STRUCTURE:
        Returns a dict like:
        {
            "app": {
                "slug": "app",
                "deployedAt": "2026-02-16T00:00:00Z"
            },
            "app1": {
                "slug": "app1",
                "deployedAt": "2026-02-16T01:00:00Z"
            }
        }

        Note: EdgeScript can work WITHOUT this mapping file!
        Subdomain directly maps to OSS path: app.metavm.tech → /projects/app/
        """
        mappings = {}

        # Get all projects with their latest successful deployment
        projects = db.query(Project).all()

        for project in projects:
            # Get latest successful deployment
            latest_deployment = (
                db.query(Deployment)
                .filter(
                    Deployment.project_id == project.id,
                    Deployment.status == DeploymentStatus.DEPLOYED
                )
                .order_by(Deployment.deployed_at.desc())
                .first()
            )

            # Add mapping (even if no deployment yet - project exists)
            if latest_deployment:
                mappings[project.slug] = {
                    "slug": project.slug,
                    "deployedAt": latest_deployment.deployed_at.isoformat() if latest_deployment.deployed_at else None
                }
            else:
                # Project exists but not deployed yet
                mappings[project.slug] = {
                    "slug": project.slug,
                    "deployedAt": None
                }

        return mappings

    def upload_mapping(self, mappings: Dict[str, dict]) -> bool:
        """
        Upload mapping JSON to OSS.

        Args:
            mappings: The subdomain mapping dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert to JSON
            json_content = json.dumps(mappings, indent=2)

            # Upload to OSS
            # Note: File will inherit bucket's ACL (should be public-read)
            self.oss_service.bucket.put_object(
                self.mapping_file,
                json_content.encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Cache-Control': 'public, max-age=60'  # Cache for 60 seconds
                }
            )

            print(f"✓ Subdomain mapping uploaded: {len(mappings)} projects")
            return True

        except Exception as e:
            print(f"✗ Failed to upload subdomain mapping: {e}")
            return False

    def update_mapping(self, db: Session) -> bool:
        """
        Generate and upload the latest mapping.

        Args:
            db: Database session

        Returns:
            True if successful
        """
        mappings = self.generate_mapping(db)
        return self.upload_mapping(mappings)

    def add_project(self, db: Session, project_slug: str) -> bool:
        """
        Add a single project to the mapping (incremental update).

        Args:
            db: Database session
            project_slug: Slug of the project to add

        Returns:
            True if successful
        """
        # For simplicity, just regenerate entire mapping
        # In production, you could fetch existing, modify, and re-upload
        return self.update_mapping(db)

    def remove_project(self, db: Session, project_slug: str) -> bool:
        """
        Remove a project from the mapping.

        Args:
            db: Database session
            project_slug: Slug of the project to remove

        Returns:
            True if successful
        """
        return self.update_mapping(db)
