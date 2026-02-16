"""
Automatic domain and CDN configuration service.

Automatically creates subdomains and configures CDN for each project.
"""
import re
from typing import Dict, Optional
from .cdn import CDNService
from ..config import get_settings

settings = get_settings()


class DomainAutomationService:
    """
    Service for automatic domain and CDN provisioning.

    For each project, automatically:
    1. Generate a subdomain (e.g., project-name.metavm.tech)
    2. Add domain to Alibaba Cloud CDN
    3. Configure DNS CNAME record
    4. Return the configured domain
    """

    def __init__(self):
        self.cdn_service = CDNService()
        self.base_domain = settings.base_domain or "metavm.tech"
        self.oss_bucket = settings.aliyun_oss_bucket
        self.oss_endpoint = settings.aliyun_oss_endpoint

    def generate_subdomain(self, project_name: str, project_id: int) -> str:
        """
        Generate a unique subdomain for a project.

        Args:
            project_name: Project name (e.g., "manul.build")
            project_id: Project ID for uniqueness

        Returns:
            Full subdomain (e.g., "manul-build.metavm.tech")
        """
        # Sanitize project name for subdomain
        # Convert to lowercase, replace special chars with hyphen
        sanitized = re.sub(r'[^a-z0-9]+', '-', project_name.lower())
        sanitized = sanitized.strip('-')

        # Limit length
        if len(sanitized) > 50:
            sanitized = sanitized[:50].rstrip('-')

        # Add project ID suffix for uniqueness (optional)
        # subdomain = f"{sanitized}-{project_id}.{self.base_domain}"

        # Use simple version without ID if name is unique enough
        subdomain = f"{sanitized}.{self.base_domain}"

        return subdomain

    def provision_project_domain(
        self,
        project_name: str,
        project_id: int,
        user_id: int
    ) -> Dict[str, any]:
        """
        Provision a complete domain setup for a project.

        Creates CDN domain, configures origin, and sets up DNS.

        Args:
            project_name: Name of the project
            project_id: Project ID
            user_id: User ID (for OSS path)

        Returns:
            Dictionary with domain info and setup status
        """
        # Generate subdomain
        subdomain = self.generate_subdomain(project_name, project_id)

        # Prepare OSS origin
        oss_origin = f"{self.oss_bucket}.{self.oss_endpoint}"

        try:
            # Add domain to CDN
            cdn_result = self.cdn_service.add_custom_domain(
                domain_name=subdomain,
                source_type="oss",
                source_content=oss_origin
            )

            if not cdn_result['success']:
                # Check if domain already exists
                if 'InvalidDomain.Duplicate' in str(cdn_result.get('error', '')):
                    # Domain already exists, get its details
                    detail_result = self.cdn_service.get_cdn_domain_detail(subdomain)

                    if detail_result['success']:
                        return {
                            'success': True,
                            'subdomain': subdomain,
                            'cname': detail_result.get('cname'),
                            'status': 'existing',
                            'message': 'Domain already configured in CDN'
                        }

                return {
                    'success': False,
                    'error': cdn_result.get('error'),
                    'message': f"Failed to add CDN domain: {cdn_result.get('error')}"
                }

            # Get domain details to retrieve CNAME
            detail_result = self.cdn_service.get_cdn_domain_detail(subdomain)

            cname = None
            if detail_result['success']:
                cname = detail_result.get('cname')

            # TODO: Auto-configure DNS if using Alibaba Cloud DNS
            # For now, return CNAME for manual configuration

            return {
                'success': True,
                'subdomain': subdomain,
                'cname': cname,
                'status': 'created',
                'message': f'CDN domain created successfully',
                'dns_instructions': f'Add CNAME record: {subdomain} → {cname}' if cname else None
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to provision domain: {str(e)}'
            }

    def configure_dns_record(
        self,
        subdomain: str,
        cname_target: str
    ) -> Dict[str, any]:
        """
        Automatically configure DNS CNAME record.

        Args:
            subdomain: The subdomain to configure (e.g., project.metavm.tech)
            cname_target: The CNAME target from CDN

        Returns:
            Dictionary with DNS configuration result
        """
        # TODO: Implement automatic DNS configuration using Alibaba Cloud DNS API
        # For now, return instructions for manual setup

        return {
            'success': False,
            'message': 'Automatic DNS configuration not yet implemented',
            'manual_instructions': {
                'record_type': 'CNAME',
                'host': subdomain.replace(f'.{self.base_domain}', ''),
                'value': cname_target,
                'ttl': 600
            }
        }

    def remove_project_domain(self, subdomain: str) -> Dict[str, any]:
        """
        Remove a project's CDN domain configuration.

        Args:
            subdomain: The subdomain to remove

        Returns:
            Dictionary with removal result
        """
        try:
            # Disable domain first
            disable_result = self.cdn_service.disable_custom_domain(subdomain)

            if not disable_result['success']:
                return disable_result

            # Delete domain
            delete_result = self.cdn_service.delete_custom_domain(subdomain)

            return delete_result

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to remove domain: {str(e)}'
            }

    def get_project_url(
        self,
        subdomain: str,
        project_id: int,
        commit_sha: str,
        user_id: int,
        file_path: str = "index.html"
    ) -> str:
        """
        Generate the full URL for a deployed project.

        Args:
            subdomain: Project's subdomain
            project_id: Project ID
            commit_sha: Commit SHA
            user_id: User ID
            file_path: File path within deployment

        Returns:
            Full URL to the deployed file
        """
        # URL format: https://subdomain/user_id/project_id/commit_sha/file_path
        return f"https://{subdomain}/{user_id}/{project_id}/{commit_sha}/{file_path}"
