"""
ESA (Edge Security Acceleration) Service for Aliyun.

Handles:
- SaaS manager creation/deletion for custom domains
- Edge KV store operations for domain-to-path routing
- SSL certificate management (automatic via ESA)
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from ..config import get_settings

settings = get_settings()


class ESAService:
    """
    Service for managing Aliyun ESA (Edge Security Acceleration).

    Features:
    - SaaS manager for custom domains
    - Edge KV store for domain routing
    - Automatic SSL provisioning
    """

    def __init__(self):
        """Initialize ESA client with credentials from settings."""
        self.client = AcsClient(
            settings.aliyun_access_key_id,
            settings.aliyun_access_key_secret,
            settings.aliyun_region
        )

        self.site_id = settings.aliyun_esa_site_id
        self.site_name = settings.aliyun_esa_site_name
        self.cname_target = settings.aliyun_esa_cname_target
        self.edge_kv_namespace_id = settings.aliyun_esa_edge_kv_namespace_id
        self.edge_kv_namespace = settings.aliyun_esa_edge_kv_namespace

    def _make_request(
        self,
        action: str,
        params: Dict[str, Any],
        version: str = "2024-09-10",
        method: str = 'POST'
    ) -> Dict[str, Any]:
        """
        Make a request to ESA API.

        Args:
            action: API action name
            params: Request parameters
            version: API version
            method: HTTP method (POST, GET, etc.)

        Returns:
            API response as dictionary
        """
        import os

        # Temporarily disable proxy for this request
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
        saved_proxies = {k: os.environ.pop(k, None) for k in proxy_vars}

        try:
            request = CommonRequest()
            # Use regional endpoint for ESA
            endpoint = f"esa.{settings.aliyun_region}.aliyuncs.com"
            request.set_domain(endpoint)
            request.set_protocol_type('https')  # Use HTTPS
            request.set_version(version)
            request.set_action_name(action)
            request.set_accept_format('json')
            request.set_method(method)

            for key, value in params.items():
                request.add_query_param(key, value)

            response = self.client.do_action_with_exception(request)
            result = json.loads(response.decode('utf-8'))

            print(f"ESA API Response - Action: {action}, Result: {result}")

            return {
                'success': True,
                'data': result
            }

        except Exception as e:
            error_msg = str(e)
            print(f"ESA API Error - Action: {action}, Error: {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'message': f'ESA API request failed: {error_msg}'
            }

        finally:
            # Restore proxy environment variables
            for key, value in saved_proxies.items():
                if value is not None:
                    os.environ[key] = value

    # ==================== Edge Routine Operations ====================

    def associate_routine_with_site(self, routine_name: str) -> Dict[str, Any]:
        """
        Associate an Edge Routine with the ESA site.

        This enables the Edge Routine to handle requests for the site.

        Args:
            routine_name: Name of the deployed Edge Routine

        Returns:
            Result with success status
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        # Try UpdateSiteDeliveryTask action
        params = {
            'SiteId': self.site_id,
            'RoutineName': routine_name,
        }

        result = self._make_request('UpdateSiteDeliveryTask', params)

        if result['success']:
            return {
                'success': True,
                'routine_name': routine_name,
                'site_id': self.site_id,
                'message': f'Edge Routine {routine_name} associated with site {self.site_name}'
            }

        return result

    def enable_routine_for_site(self, routine_name: str, enabled: bool = True) -> Dict[str, Any]:
        """
        Enable or disable an Edge Routine for the site.

        Args:
            routine_name: Name of the Edge Routine
            enabled: True to enable, False to disable

        Returns:
            Result with success status
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'RoutineName': routine_name,
            'Enabled': str(enabled).lower(),
        }

        result = self._make_request('UpdateRoutineStatus', params)

        if result['success']:
            return {
                'success': True,
                'routine_name': routine_name,
                'enabled': enabled,
                'message': f'Edge Routine {routine_name} {"enabled" if enabled else "disabled"}'
            }

        return result

    # ==================== SaaS Manager Operations ====================

    def create_saas_manager(self, domain: str) -> Dict[str, Any]:
        """
        Create SaaS manager (Custom Hostname) for a custom domain.

        Uses ESA API: CreateCustomHostname
        Doc: https://help.aliyun.com/zh/edge-security-acceleration/esa/api-esa-2024-09-10-createcustomhostname

        SaaS manager enables:
        - Custom domain on ESA site
        - Automatic SSL certificate provisioning
        - Domain-level configuration

        Args:
            domain: Custom domain name (e.g., "app.example.com")

        Returns:
            Result with custom_hostname_id if successful
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        # Step 1: Create custom hostname with SSL off (required by API)
        params = {
            'SiteId': self.site_id,
            'Hostname': domain,
            'RecordId': '4513850898327424',  # cname.metavm.tech DNS record ID
            'SslFlag': 'off',  # Must be 'off' during creation
            'CertificateId': '0'  # Placeholder for auto SSL
        }

        result = self._make_request('CreateCustomHostname', params)

        if not result['success']:
            return result

        data = result['data']
        hostname_id = str(data.get('HostnameId'))

        # Step 2: Enable SSL with free certificate
        update_params = {
            'SiteId': self.site_id,
            'HostnameId': hostname_id,
            'CertType': 'free',  # Use free SSL certificate
            'SslFlag': 'on'  # Enable SSL
        }

        update_result = self._make_request('UpdateCustomHostname', update_params)

        if not update_result['success']:
            # SSL enablement failed, but hostname is created
            return {
                'success': True,
                'custom_hostname_id': hostname_id,
                'hostname': domain,
                'cname': self.cname_target,
                'ssl_enabled': False,
                'ssl_error': update_result.get('error'),
                'message': f'Custom hostname created for {domain} but SSL enablement failed'
            }

        return {
            'success': True,
            'custom_hostname_id': hostname_id,
            'hostname': domain,
            'cname': self.cname_target,
            'ssl_enabled': True,
            'message': f'Custom hostname created for {domain} with SSL enabled'
        }

    def verify_custom_hostname(self, hostname_id: str) -> Dict[str, Any]:
        """
        Verify custom hostname using ESA's verification mechanism.

        Uses ESA API: VerifyCustomHostname
        Doc: https://help.aliyun.com/zh/edge-security-acceleration/esa/api-esa-2024-09-10-verifycustomhostname

        Args:
            hostname_id: Custom hostname ID to verify

        Returns:
            Verification result
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'HostnameId': hostname_id,
        }

        result = self._make_request('VerifyCustomHostname', params)

        if result['success']:
            return {
                'success': True,
                'hostname_id': hostname_id,
                'message': 'Custom hostname verification initiated'
            }

        return result

    def delete_saas_manager(self, custom_hostname_id: str) -> Dict[str, Any]:
        """
        Delete SaaS manager (Custom Hostname) for a custom domain.

        Uses ESA API: DeleteCustomHostname

        Args:
            custom_hostname_id: Custom hostname ID to delete

        Returns:
            Deletion result
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'HostnameId': custom_hostname_id,
        }

        result = self._make_request('DeleteCustomHostname', params)

        if result['success']:
            return {
                'success': True,
                'custom_hostname_id': custom_hostname_id,
                'message': f'Custom hostname deleted: {custom_hostname_id}'
            }

        return result

    def get_custom_hostname_status(self, hostname_id: str) -> Dict[str, Any]:
        """
        Get custom hostname status including ICP check.

        Uses ESA API: GetCustomHostname
        Doc: https://help.aliyun.com/zh/edge-security-acceleration/esa/api-esa-2024-09-10-getcustomhostname

        Args:
            hostname_id: Custom hostname ID

        Returns:
            Status information including ICP status
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'HostnameId': hostname_id,
        }

        result = self._make_request('GetCustomHostname', params)

        if result['success']:
            data = result['data']
            model = data.get('CustomHostnameModel', {})

            return {
                'success': True,
                'hostname': model.get('Hostname'),
                'status': model.get('Status'),
                'offline_reason': model.get('OfflineReason'),
                'ssl_flag': model.get('SslFlag'),
                'cert_status': model.get('CertStatus'),
                'cert_apply_message': model.get('CertApplyMessage'),  # The actual cert status: 'issued', 'issuing', etc.
                'cert_type': model.get('CertType'),
                'cert_not_after': model.get('CertNotAfter'),
                'icp_required': model.get('OfflineReason') == 'missing_icp',
                'verified': model.get('Status') in ['active', 'online']
            }

        return result

    def get_saas_manager_status(self, domain: str) -> Dict[str, Any]:
        """
        Get SaaS manager status and SSL certificate info.

        Args:
            domain: Custom domain name

        Returns:
            Status information including SSL state
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'Domain': domain,
        }

        result = self._make_request('GetSiteSaasDomain', params)

        if result['success']:
            data = result['data']
            domain_info = data.get('DomainInfo', {})

            return {
                'success': True,
                'domain': domain,
                'status': domain_info.get('Status'),
                'ssl_status': domain_info.get('SslStatus'),
                'cname': domain_info.get('Cname'),
                'verified': domain_info.get('Status') == 'online'
            }

        return result

    # ==================== Edge KV Operations ====================

    def put_edge_kv(self, key: str, value: str) -> Dict[str, Any]:
        """
        Put key-value pair into Edge KV store.

        Args:
            key: Domain name (e.g., "app.example.com")
            value: JSON string with routing info

        Returns:
            Operation result
        """
        if not self.edge_kv_namespace_id:
            return {
                'success': False,
                'error': 'Edge KV namespace ID not configured'
            }

        params = {
            'Namespace': self.edge_kv_namespace,
            'Key': key,
            'Value': value,
        }

        result = self._make_request('PutKv', params)

        if result['success']:
            return {
                'success': True,
                'key': key,
                'message': f'Edge KV updated for {key}'
            }

        return result

    def get_edge_kv(self, key: str) -> Dict[str, Any]:
        """
        Get value from Edge KV store.

        Args:
            key: Domain name

        Returns:
            Value if found
        """
        if not self.edge_kv_namespace_id:
            return {
                'success': False,
                'error': 'Edge KV namespace ID not configured'
            }

        params = {
            'Namespace': self.edge_kv_namespace,
            'Key': key,
        }

        result = self._make_request('GetKv', params)

        if result['success']:
            data = result['data']
            return {
                'success': True,
                'key': key,
                'value': data.get('Value'),
            }

        return result

    def delete_edge_kv(self, key: str) -> Dict[str, Any]:
        """
        Delete key from Edge KV store.

        Note: Aliyun ESA DeleteKv API uses GET method (not POST or DELETE).

        Args:
            key: Domain name

        Returns:
            Deletion result
        """
        if not self.edge_kv_namespace_id:
            return {
                'success': False,
                'error': 'Edge KV namespace ID not configured'
            }

        params = {
            'Namespace': self.edge_kv_namespace,
            'Key': key,
        }

        # DeleteKv API requires GET method
        result = self._make_request('DeleteKv', params, method='GET')

        if result['success']:
            return {
                'success': True,
                'key': key,
                'message': f'Edge KV deleted for {key}'
            }

        return result

    # ==================== High-Level Domain Management ====================

    def update_edge_kv_mapping(
        self,
        domain: str,
        user_id: int,
        project_id: int,
        deployment_id: int,
        commit_sha: str,
        project_type: str = "static",
        fc_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update Edge KV store with domain-to-path mapping.

        This is called when:
        - Domain is verified (initial mapping)
        - Deployment is promoted to domain
        - Auto-update triggers on new deployment

        Args:
            domain: Custom domain name
            user_id: Project owner user ID
            project_id: Project ID
            deployment_id: Active deployment ID
            commit_sha: Deployment commit SHA
            project_type: "static" or "python"
            fc_endpoint: FC endpoint URL (required for Python projects)

        Returns:
            Update result
        """
        from ..database import SessionLocal
        from ..models import Project

        db = SessionLocal()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return {
                    'success': False,
                    'error': f'Project {project_id} not found'
                }

            # Determine project type from model if not explicitly passed
            effective_type = project_type
            if hasattr(project, 'project_type') and project.project_type:
                effective_type = project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type)

            effective_fc_endpoint = fc_endpoint or (project.fc_endpoint_url if hasattr(project, 'fc_endpoint_url') else None)

            if effective_type == "python":
                kv_value = {
                    'type': 'python',
                    'fc_endpoint': effective_fc_endpoint,
                    'project_slug': project.slug,
                    'deployment_id': deployment_id,
                    'commit_sha': commit_sha,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                }
            else:
                oss_path = f"projects/{project.slug}/{deployment_id}"
                kv_value = {
                    'type': 'static',
                    'project_slug': project.slug,
                    'deployment_id': deployment_id,
                    'commit_sha': commit_sha,
                    'oss_path': oss_path,
                    'is_spa': project.is_spa,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                }
        finally:
            db.close()

        result = self.put_edge_kv(domain, json.dumps(kv_value))

        if result['success']:
            return {
                'success': True,
                'domain': domain,
                'oss_path': kv_value.get('oss_path'),
                'fc_endpoint': kv_value.get('fc_endpoint'),
                'deployment_id': deployment_id,
                'message': f'Edge KV mapping updated for {domain}',
            }

        return result

    def delete_edge_kv_mapping(self, domain: str) -> Dict[str, Any]:
        """
        Delete domain mapping from Edge KV.

        Called when domain is deleted.

        Args:
            domain: Custom domain name

        Returns:
            Deletion result
        """
        return self.delete_edge_kv(domain)

    def provision_custom_domain(
        self,
        domain: str,
        user_id: int,
        project_id: int,
        deployment_id: int,
        commit_sha: str
    ) -> Dict[str, Any]:
        """
        Full provisioning flow for custom domain.

        Two types of domains:
        1. *.metavm.tech subdomains: Must be added manually via ESA console
           - Only Edge KV is configured via API
           - User adds domain via ESA console UI

        2. External domains (e.g., app.example.com):
           - CreateCustomHostname API (requires RecordId)
           - Edge KV configured via API
           - Fully automated

        Steps:
        1. Detect domain type
        2. For external domains: Create Custom Hostname
        3. Update Edge KV mapping (enables routing)

        Args:
            domain: Custom domain name
            user_id: Project owner user ID
            project_id: Project ID
            deployment_id: Active deployment ID
            commit_sha: Deployment commit SHA

        Returns:
            Provisioning result
        """
        is_metavm_subdomain = domain.endswith('.metavm.tech') or domain == 'metavm.tech'
        custom_hostname_id = None

        # Step 1: Create Custom Hostname (only for external domains)
        if not is_metavm_subdomain:
            # External domain - use CreateCustomHostname API
            # Note: Requires RecordId (domain must be added to ESA first)
            saas_result = self.create_saas_manager(domain)

            if not saas_result['success']:
                return {
                    'success': False,
                    'error': 'Failed to create custom hostname. Domain must be added to ESA site first.',
                    'details': saas_result
                }

            custom_hostname_id = saas_result.get('custom_hostname_id')
        # else: metavm.tech subdomain - skip API, user must add via ESA console

        # Step 2: Update Edge KV mapping
        kv_result = self.update_edge_kv_mapping(
            domain, user_id, project_id, deployment_id, commit_sha
        )

        if not kv_result['success']:
            # Rollback: delete custom hostname if it was created
            if custom_hostname_id:
                self.delete_saas_manager(custom_hostname_id)
            return {
                'success': False,
                'error': 'Failed to update Edge KV mapping',
                'details': kv_result
            }

        result = {
            'success': True,
            'domain': domain,
            'custom_hostname_id': custom_hostname_id,
            'cname': self.cname_target,
            'oss_path': kv_result.get('oss_path'),
        }

        if is_metavm_subdomain:
            result['message'] = f'Edge KV configured for {domain}. Add domain to ESA site via console.'
            result['manual_step_required'] = True
            result['instructions'] = {
                'note': 'metavm.tech subdomains must be added via ESA Console',
                'url': 'https://esa.console.aliyun.com/',
                'action': f'Add {domain} to site metavm.tech'
            }
        else:
            result['message'] = f'Custom domain {domain} provisioned successfully'

        return result

    def deprovision_custom_domain(self, domain: str, custom_hostname_id: str) -> Dict[str, Any]:
        """
        Full deprovisioning flow for custom domain.

        Steps:
        1. Delete Edge KV mapping
        2. Delete SaaS manager (Custom Hostname)

        Args:
            domain: Custom domain name
            custom_hostname_id: ESA Custom Hostname ID (esa_saas_id)

        Returns:
            Deprovisioning result
        """
        errors = []

        # Step 1: Delete Edge KV mapping
        kv_result = self.delete_edge_kv_mapping(domain)
        if not kv_result['success']:
            errors.append(f"KV deletion: {kv_result.get('error')}")

        # Step 2: Delete SaaS manager (Custom Hostname)
        saas_result = self.delete_saas_manager(custom_hostname_id)
        if not saas_result['success']:
            errors.append(f"SaaS deletion: {saas_result.get('error')}")

        if errors:
            return {
                'success': False,
                'domain': domain,
                'errors': errors,
                'message': f'Partial deprovisioning failure: {"; ".join(errors)}'
            }

        return {
            'success': True,
            'domain': domain,
            'message': f'Custom domain {domain} deprovisioned successfully'
        }

    # ==================== Cache Management ====================

    def purge_cache(self, paths: List[str]) -> Dict[str, Any]:
        """
        Purge ESA cache for specific file URLs.

        Args:
            paths: List of full URLs to purge

        Returns:
            Purge result
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'Type': 'file',
            'Content': json.dumps({'Files': paths}),
        }

        result = self._make_request('PurgeCaches', params)

        if result['success']:
            return {
                'success': True,
                'paths': paths,
                'message': f'Cache purged for {len(paths)} paths'
            }

        return result

    def purge_host_cache(self, hostnames: List[str]) -> Dict[str, Any]:
        """
        Purge all ESA cache for given hostnames.

        Args:
            hostnames: List of hostnames (e.g., ["slug.metavm.tech"])

        Returns:
            Purge result
        """
        if not self.site_id:
            return {
                'success': False,
                'error': 'ESA site ID not configured'
            }

        params = {
            'SiteId': self.site_id,
            'Type': 'hostname',
            'Content': json.dumps({'Hostnames': hostnames}),
        }

        result = self._make_request('PurgeCaches', params)

        if result['success']:
            return {
                'success': True,
                'hostnames': hostnames,
                'message': f'Cache purged for {", ".join(hostnames)}'
            }

        return result
