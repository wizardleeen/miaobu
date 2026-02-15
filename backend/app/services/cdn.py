from aliyunsdkcore.client import AcsClient
from aliyunsdkcdn.request.v20180510 import (
    RefreshObjectCachesRequest,
    PushObjectCacheRequest,
    DescribeRefreshTasksRequest,
    DescribeCdnDomainDetailRequest,
    AddCdnDomainRequest,
    DeleteCdnDomainRequest,
    BatchStartCdnDomainRequest,
    BatchStopCdnDomainRequest
)
from typing import List, Dict, Optional
import time

from ..config import get_settings

settings = get_settings()


class CDNService:
    """
    Service for interacting with Alibaba Cloud CDN.

    Handles cache purging, cache warming, and CDN configuration.
    """

    def __init__(self):
        """Initialize CDN client with credentials from settings."""
        self.client = AcsClient(
            settings.aliyun_access_key_id,
            settings.aliyun_access_key_secret,
            settings.aliyun_region
        )

        self.cdn_domain = settings.aliyun_cdn_domain

    def refresh_object_cache(
        self,
        object_paths: List[str],
        object_type: str = "File"
    ) -> Dict[str, any]:
        """
        Refresh (purge) CDN cache for specific objects.

        Args:
            object_paths: List of full URLs or directory paths to purge
            object_type: "File" for specific files, "Directory" for directories

        Returns:
            Dictionary with purge task ID and request ID
        """
        if not self.cdn_domain:
            return {
                'success': False,
                'error': 'CDN domain not configured'
            }

        # Create refresh request
        request = RefreshObjectCachesRequest.RefreshObjectCachesRequest()
        request.set_accept_format('json')

        # Join paths with newline (API requirement)
        request.set_ObjectPath('\n'.join(object_paths))
        request.set_ObjectType(object_type)

        try:
            # Execute request
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'task_id': result.get('RefreshTaskId'),
                'request_id': result.get('RequestId'),
                'object_paths': object_paths,
                'object_type': object_type
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'object_paths': object_paths
            }

    def refresh_directory(self, directory_url: str) -> Dict[str, any]:
        """
        Refresh entire directory in CDN cache.

        Args:
            directory_url: Full URL to directory (must end with /)

        Returns:
            Purge operation result
        """
        if not directory_url.endswith('/'):
            directory_url += '/'

        return self.refresh_object_cache([directory_url], object_type="Directory")

    def push_object_cache(self, object_paths: List[str]) -> Dict[str, any]:
        """
        Warm up (pre-fetch) CDN cache for specific objects.

        Args:
            object_paths: List of full URLs to pre-fetch

        Returns:
            Dictionary with push task ID and request ID
        """
        if not self.cdn_domain:
            return {
                'success': False,
                'error': 'CDN domain not configured'
            }

        request = PushObjectCacheRequest.PushObjectCacheRequest()
        request.set_accept_format('json')
        request.set_ObjectPath('\n'.join(object_paths))

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'task_id': result.get('PushTaskId'),
                'request_id': result.get('RequestId'),
                'object_paths': object_paths
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'object_paths': object_paths
            }

    def describe_refresh_tasks(
        self,
        task_id: Optional[str] = None,
        domain_name: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Query refresh/purge task status.

        Args:
            task_id: Specific task ID to query
            domain_name: CDN domain name to filter
            status: Task status to filter (Complete, Refreshing, Failed)

        Returns:
            Dictionary with task information
        """
        request = DescribeRefreshTasksRequest.DescribeRefreshTasksRequest()
        request.set_accept_format('json')

        if task_id:
            request.set_TaskId(task_id)
        if domain_name:
            request.set_DomainName(domain_name)
        if status:
            request.set_Status(status)

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'tasks': result.get('Tasks', {}).get('CDNTask', []),
                'total_count': result.get('TotalCount', 0)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def wait_for_refresh_completion(
        self,
        task_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> Dict[str, any]:
        """
        Wait for a refresh task to complete.

        Args:
            task_id: Task ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Dictionary with final task status
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Query task status
            result = self.describe_refresh_tasks(task_id=task_id)

            if not result['success']:
                return result

            tasks = result.get('tasks', [])
            if not tasks:
                return {
                    'success': False,
                    'error': f'Task {task_id} not found'
                }

            task = tasks[0]
            status = task.get('Status')

            if status == 'Complete':
                return {
                    'success': True,
                    'status': 'Complete',
                    'task': task
                }
            elif status == 'Failed':
                return {
                    'success': False,
                    'status': 'Failed',
                    'error': task.get('Description', 'Unknown error'),
                    'task': task
                }

            # Still refreshing, wait and retry
            time.sleep(poll_interval)

        # Timeout
        return {
            'success': False,
            'error': f'Timeout waiting for task {task_id} after {timeout}s',
            'status': 'Timeout'
        }

    def get_cdn_domain_detail(self, domain_name: Optional[str] = None) -> Dict[str, any]:
        """
        Get CDN domain configuration details.

        Args:
            domain_name: CDN domain name (uses configured domain if not provided)

        Returns:
            Dictionary with domain details
        """
        domain = domain_name or self.cdn_domain

        if not domain:
            return {
                'success': False,
                'error': 'CDN domain not configured'
            }

        request = DescribeCdnDomainDetailRequest.DescribeCdnDomainDetailRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain)

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            domain_detail = result.get('GetDomainDetailModel', {})

            return {
                'success': True,
                'domain': domain_detail.get('DomainName'),
                'cname': domain_detail.get('Cname'),
                'status': domain_detail.get('DomainStatus'),
                'source': domain_detail.get('Sources', {}).get('Source', []),
                'ssl': domain_detail.get('CertInfo')
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def generate_cdn_url(self, oss_url: str) -> str:
        """
        Convert OSS URL to CDN URL.

        Args:
            oss_url: Original OSS URL

        Returns:
            CDN URL (or original URL if CDN not configured)
        """
        if not self.cdn_domain:
            return oss_url

        # Extract path from OSS URL
        # OSS URL format: https://{bucket}.{endpoint}/{path}
        # CDN URL format: https://{cdn_domain}/{path}

        try:
            # Parse OSS URL
            from urllib.parse import urlparse
            parsed = urlparse(oss_url)

            # Replace domain with CDN domain
            cdn_url = f"https://{self.cdn_domain}{parsed.path}"

            if parsed.query:
                cdn_url += f"?{parsed.query}"

            return cdn_url

        except Exception:
            # Fallback to original URL
            return oss_url

    def purge_deployment_cache(
        self,
        user_id: int,
        project_id: int,
        commit_sha: str,
        wait_for_completion: bool = False
    ) -> Dict[str, any]:
        """
        Purge CDN cache for a specific deployment.

        Args:
            user_id: User ID
            project_id: Project ID
            commit_sha: Commit SHA
            wait_for_completion: Whether to wait for purge to complete

        Returns:
            Purge operation result
        """
        if not self.cdn_domain:
            return {
                'success': False,
                'error': 'CDN domain not configured'
            }

        # Construct directory URL
        directory_path = f"{user_id}/{project_id}/{commit_sha}/"
        directory_url = f"https://{self.cdn_domain}/{directory_path}"

        # Purge directory
        result = self.refresh_directory(directory_url)

        if not result['success']:
            return result

        # Optionally wait for completion
        if wait_for_completion and result.get('task_id'):
            completion_result = self.wait_for_refresh_completion(
                result['task_id'],
                timeout=60  # 1 minute timeout for directory purge
            )

            return {
                **result,
                'completion_status': completion_result.get('status'),
                'completed': completion_result.get('success', False)
            }

        return result

    def add_custom_domain(
        self,
        domain_name: str,
        source_type: str = "oss",
        source_content: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Add a custom domain to CDN.

        Args:
            domain_name: Custom domain to add (e.g., "www.example.com")
            source_type: Origin server type ("oss", "ipaddr", "domain")
            source_content: Origin server address (OSS bucket domain or IP/domain)

        Returns:
            Dictionary with operation result
        """
        if not source_content:
            # Use configured OSS as default source
            source_content = f"{settings.aliyun_oss_bucket}.{settings.aliyun_oss_endpoint}"

        request = AddCdnDomainRequest.AddCdnDomainRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain_name)
        request.set_CdnType("download")  # For static file distribution
        request.set_Sources(f'[{{"content":"{source_content}","type":"{source_type}","priority":"20","port":80}}]')

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'domain_name': domain_name,
                'request_id': result.get('RequestId'),
                'message': 'Custom domain added successfully'
            }

        except Exception as e:
            error_msg = str(e)

            # Parse common errors
            if "InvalidDomain.Duplicate" in error_msg:
                return {
                    'success': False,
                    'error': 'Domain already exists in CDN',
                    'message': 'This domain is already configured in CDN'
                }
            elif "InvalidDomain.NotRegistered" in error_msg:
                return {
                    'success': False,
                    'error': 'Domain not registered or verified',
                    'message': 'Please register and verify domain ownership first'
                }
            else:
                return {
                    'success': False,
                    'error': error_msg,
                    'message': f'Failed to add custom domain: {error_msg}'
                }

    def delete_custom_domain(self, domain_name: str) -> Dict[str, any]:
        """
        Delete a custom domain from CDN.

        Args:
            domain_name: Custom domain to delete

        Returns:
            Dictionary with operation result
        """
        request = DeleteCdnDomainRequest.DeleteCdnDomainRequest()
        request.set_accept_format('json')
        request.set_DomainName(domain_name)

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'domain_name': domain_name,
                'request_id': result.get('RequestId'),
                'message': 'Custom domain deleted successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to delete custom domain: {str(e)}'
            }

    def enable_custom_domain(self, domain_name: str) -> Dict[str, any]:
        """
        Enable (start) a custom domain in CDN.

        Args:
            domain_name: Custom domain to enable

        Returns:
            Dictionary with operation result
        """
        request = BatchStartCdnDomainRequest.BatchStartCdnDomainRequest()
        request.set_accept_format('json')
        request.set_DomainNames(domain_name)

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'domain_name': domain_name,
                'request_id': result.get('RequestId'),
                'message': 'Custom domain enabled successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to enable custom domain: {str(e)}'
            }

    def disable_custom_domain(self, domain_name: str) -> Dict[str, any]:
        """
        Disable (stop) a custom domain in CDN.

        Args:
            domain_name: Custom domain to disable

        Returns:
            Dictionary with operation result
        """
        request = BatchStopCdnDomainRequest.BatchStopCdnDomainRequest()
        request.set_accept_format('json')
        request.set_DomainNames(domain_name)

        try:
            response = self.client.do_action_with_exception(request)
            result = eval(response.decode('utf-8'))

            return {
                'success': True,
                'domain_name': domain_name,
                'request_id': result.get('RequestId'),
                'message': 'Custom domain disabled successfully'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to disable custom domain: {str(e)}'
            }
