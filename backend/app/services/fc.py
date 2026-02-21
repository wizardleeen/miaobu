"""
Function Compute (FC) Service using FC 3.0 SDK.

Manages serverless function deployment using code package mode.
Uses custom.debian10 runtime with a Python 3.10 layer for modern framework support.
User Python apps listen on port 9000.
"""
import json
import time
from typing import Dict, Any, Optional

from alibabacloud_fc20230330.client import Client as FCClient
from alibabacloud_fc20230330 import models as fc_models
from alibabacloud_tea_openapi import models as open_api_models

from ..config import get_settings

# Python 3.10 layer ARN (pre-built standalone Python binary)
PYTHON_LAYER_ARN = 'acs:fc:cn-qingdao:1765215622020297:layers/python310/versions/1'

# Node.js 20 layer ARN (pre-built standalone Node.js binary)
NODEJS_LAYER_ARN = 'acs:fc:cn-qingdao:1765215622020297:layers/nodejs20/versions/1'


class FCService:
    """
    Service for managing Aliyun Function Compute functions.

    Uses FC 3.0 API with code package mode (zip uploaded to OSS).
    The custom.debian10 runtime is augmented with a Python 3.10 layer.
    """

    def __init__(self):
        """Initialize FC 3.0 client with credentials from settings."""
        settings = get_settings()
        self.settings = settings
        fc_region = settings.aliyun_fc_region
        config = open_api_models.Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
            endpoint=f'{settings.aliyun_account_id}.{fc_region}.fc.aliyuncs.com',
        )
        self.client = FCClient(config)
        self.account_id = settings.aliyun_account_id
        self.region = fc_region

    def _get_vpc_config(self) -> Optional[fc_models.VPCConfig]:
        """Build VPC configuration if VPC settings are provided."""
        settings = self.settings
        if settings.aliyun_fc_vpc_id and settings.aliyun_fc_vswitch_id:
            return fc_models.VPCConfig(
                vpc_id=settings.aliyun_fc_vpc_id,
                vswitch_ids=[settings.aliyun_fc_vswitch_id],
                security_group_id=settings.aliyun_fc_security_group_id if settings.aliyun_fc_security_group_id else None,
            )
        return None

    def create_or_update_function(
        self,
        name: str,
        oss_bucket: str,
        oss_key: str,
        start_command: str,
        python_version: str = "3.10",
        env_vars: Optional[Dict[str, str]] = None,
        memory_mb: int = 512,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Create or update an FC function with code from OSS.

        Uses custom.debian10 runtime with Python 3.10 layer.
        The layer provides /opt/python/bin/python3 which is used to run the app.

        Args:
            name: Function name (e.g., "miaobu-my-app")
            oss_bucket: OSS bucket containing the code zip
            oss_key: OSS object key for the code zip
            start_command: Shell command to start the app (e.g., "uvicorn main:app ...")
            python_version: Python version (for logging, actual runtime is from layer)
            env_vars: Environment variables for the function
            memory_mb: Memory allocation in MB
            timeout: Function timeout in seconds

        Returns:
            Result dict with endpoint_url if successful
        """
        code = fc_models.InputCodeLocation(
            oss_bucket_name=oss_bucket,
            oss_object_name=oss_key,
        )

        # Normalize the start command to use the layer's Python
        # Replace bare tool names (uvicorn, gunicorn, flask) with python -m equivalents
        normalized_cmd = start_command
        for tool in ('uvicorn', 'gunicorn', 'flask', 'django'):
            if normalized_cmd.startswith(tool + ' ') or normalized_cmd == tool:
                normalized_cmd = f'/opt/python/bin/python3 -m {normalized_cmd}'
                break
        else:
            # If the command starts with 'python' or 'python3', replace with layer's python
            if normalized_cmd.startswith('python3 ') or normalized_cmd.startswith('python '):
                parts = normalized_cmd.split(' ', 1)
                normalized_cmd = f'/opt/python/bin/python3 {parts[1]}'

        # Bootstrap: set PYTHONPATH for bundled deps + layer's Python site-packages
        bootstrap_cmd = (
            f'export PATH=/opt/python/bin:$PATH '
            f'&& export PYTHONPATH=$(pwd)/python_deps:$PYTHONPATH '
            f'&& exec {normalized_cmd}'
        )

        custom_runtime = fc_models.CustomRuntimeConfig(
            command=["/bin/bash", "-c", bootstrap_cmd],
            port=9000,
        )

        vpc_config = self._get_vpc_config()
        is_update = False

        try:
            create_input = fc_models.CreateFunctionInput(
                function_name=name,
                runtime='custom.debian10',
                handler='index.handler',
                code=code,
                custom_runtime_config=custom_runtime,
                memory_size=memory_mb,
                timeout=timeout,
                internet_access=True,
                environment_variables=env_vars or {},
                layers=[PYTHON_LAYER_ARN],
                vpc_config=vpc_config,
            )
            request = fc_models.CreateFunctionRequest(body=create_input)
            self.client.create_function(request)
            print(f"FC: Created function {name}")

        except Exception as e:
            if 'FunctionAlreadyExists' in str(e):
                # Update existing function — merge new env vars into existing
                is_update = True
                merged_env = {}
                try:
                    existing = self.client.get_function(name, fc_models.GetFunctionRequest())
                    merged_env = dict(existing.body.environment_variables or {})
                except Exception:
                    pass
                merged_env.update(env_vars or {})

                update_input = fc_models.UpdateFunctionInput(
                    runtime='custom.debian10',
                    handler='index.handler',
                    code=code,
                    custom_runtime_config=custom_runtime,
                    memory_size=memory_mb,
                    timeout=timeout,
                    internet_access=True,
                    environment_variables=merged_env,
                    layers=[PYTHON_LAYER_ARN],
                    vpc_config=vpc_config,
                )
                update_request = fc_models.UpdateFunctionRequest(body=update_input)
                self.client.update_function(name, update_request)
                print(f"FC: Updated function {name}")
            else:
                print(f"FC: Error creating function {name}: {e}")
                return {
                    'success': False,
                    'error': str(e),
                }

        # Ensure HTTP trigger exists (for the function to be accessible via HTTP)
        endpoint_url = self._ensure_http_trigger(name)

        if not endpoint_url:
            return {
                'success': False,
                'error': 'Failed to create HTTP trigger',
            }

        action = 'updated' if is_update else 'created'
        return {
            'success': True,
            'function_name': name,
            'endpoint_url': endpoint_url,
            'message': f'Function {name} {action} successfully',
        }

    def create_or_update_node_function(
        self,
        name: str,
        oss_bucket: str,
        oss_key: str,
        start_command: str,
        env_vars: Optional[Dict[str, str]] = None,
        memory_mb: int = 512,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Create or update an FC function for a Node.js backend app.

        Uses custom.debian10 runtime with Node.js 20 layer.
        The layer provides /opt/nodejs/bin/node and /opt/nodejs/bin/npm.

        Args:
            name: Function name (e.g., "miaobu-my-app")
            oss_bucket: OSS bucket containing the code zip
            oss_key: OSS object key for the code zip
            start_command: Shell command to start the app (e.g., "npm start")
            env_vars: Environment variables for the function
            memory_mb: Memory allocation in MB
            timeout: Function timeout in seconds

        Returns:
            Result dict with endpoint_url if successful
        """
        code = fc_models.InputCodeLocation(
            oss_bucket_name=oss_bucket,
            oss_object_name=oss_key,
        )

        # Normalize the start command to use the layer's Node.js
        # npm/npx scripts have broken relative requires in the layer,
        # so route them through node + npm-cli.js directly
        normalized_cmd = start_command
        if normalized_cmd.startswith('npm ') or normalized_cmd == 'npm':
            npm_args = normalized_cmd[4:] if normalized_cmd.startswith('npm ') else ''
            normalized_cmd = f'/opt/nodejs/bin/node /opt/nodejs/lib/node_modules/npm/bin/npm-cli.js {npm_args}'.strip()
        elif normalized_cmd.startswith('npx '):
            npx_args = normalized_cmd[4:]
            normalized_cmd = f'/opt/nodejs/bin/node /opt/nodejs/lib/node_modules/npm/bin/npx-cli.js {npx_args}'
        elif normalized_cmd.startswith('node ') or normalized_cmd == 'node':
            normalized_cmd = f'/opt/nodejs/bin/{normalized_cmd}'

        # Bootstrap: set PATH for layer's Node.js binaries
        bootstrap_cmd = (
            f'export PATH=/opt/nodejs/bin:$PATH '
            f'&& export NODE_ENV=production '
            f'&& export PORT=9000 '
            f'&& exec {normalized_cmd}'
        )

        custom_runtime = fc_models.CustomRuntimeConfig(
            command=["/bin/bash", "-c", bootstrap_cmd],
            port=9000,
        )

        vpc_config = self._get_vpc_config()
        is_update = False

        try:
            create_input = fc_models.CreateFunctionInput(
                function_name=name,
                runtime='custom.debian10',
                handler='index.handler',
                code=code,
                custom_runtime_config=custom_runtime,
                memory_size=memory_mb,
                timeout=timeout,
                internet_access=True,
                environment_variables=env_vars or {},
                layers=[NODEJS_LAYER_ARN],
                vpc_config=vpc_config,
            )
            request = fc_models.CreateFunctionRequest(body=create_input)
            self.client.create_function(request)
            print(f"FC: Created Node.js function {name}")

        except Exception as e:
            if 'FunctionAlreadyExists' in str(e):
                is_update = True
                merged_env = {}
                try:
                    existing = self.client.get_function(name, fc_models.GetFunctionRequest())
                    merged_env = dict(existing.body.environment_variables or {})
                except Exception:
                    pass
                merged_env.update(env_vars or {})

                update_input = fc_models.UpdateFunctionInput(
                    runtime='custom.debian10',
                    handler='index.handler',
                    code=code,
                    custom_runtime_config=custom_runtime,
                    memory_size=memory_mb,
                    timeout=timeout,
                    internet_access=True,
                    environment_variables=merged_env,
                    layers=[NODEJS_LAYER_ARN],
                    vpc_config=vpc_config,
                )
                update_request = fc_models.UpdateFunctionRequest(body=update_input)
                self.client.update_function(name, update_request)
                print(f"FC: Updated Node.js function {name}")
            else:
                print(f"FC: Error creating Node.js function {name}: {e}")
                return {
                    'success': False,
                    'error': str(e),
                }

        endpoint_url = self._ensure_http_trigger(name)

        if not endpoint_url:
            return {
                'success': False,
                'error': 'Failed to create HTTP trigger',
            }

        action = 'updated' if is_update else 'created'
        return {
            'success': True,
            'function_name': name,
            'endpoint_url': endpoint_url,
            'message': f'Node.js function {name} {action} successfully',
        }

    def _extract_trigger_url(self, response_body) -> Optional[str]:
        """Extract HTTP trigger URL from various possible response formats."""
        # Try response.body.http_trigger first
        http_trigger = getattr(response_body, 'http_trigger', None)
        if http_trigger:
            if isinstance(http_trigger, dict):
                url = http_trigger.get('urlInternet') or http_trigger.get('url_internet')
                if url:
                    return url
            else:
                url = getattr(http_trigger, 'url_internet', None) or getattr(http_trigger, 'urlInternet', None)
                if url:
                    return url
                # Log what attributes http_trigger has for debugging
                print(f"FC: http_trigger attrs: {[a for a in dir(http_trigger) if not a.startswith('_')]}")

        # Try response.body directly (some SDK versions put URL here)
        for attr in ('url_internet', 'urlInternet', 'internet_url'):
            url = getattr(response_body, attr, None)
            if url:
                return url

        # Try treating body as dict
        if isinstance(response_body, dict):
            url = (response_body.get('httpTrigger', {}).get('urlInternet')
                   or response_body.get('http_trigger', {}).get('url_internet'))
            if url:
                return url

        # Log body attributes for debugging
        print(f"FC: response body type={type(response_body).__name__}, "
              f"attrs={[a for a in dir(response_body) if not a.startswith('_')]}")
        return None

    def _ensure_http_trigger(self, function_name: str) -> Optional[str]:
        """
        Ensure an HTTP trigger exists for the function.

        Returns the internet URL from the trigger, or None on failure.
        """
        trigger_config = json.dumps({
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            "authType": "anonymous",
        })

        try:
            trigger_input = fc_models.CreateTriggerInput(
                trigger_name='http-trigger',
                trigger_type='http',
                trigger_config=trigger_config,
            )
            trigger_request = fc_models.CreateTriggerRequest(body=trigger_input)
            response = self.client.create_trigger(function_name, trigger_request)

            url = self._extract_trigger_url(response.body)
            if url:
                return url
            print(f"FC: Trigger created for {function_name} but URL extraction failed")
            return None

        except Exception as e:
            if 'TriggerAlreadyExists' in str(e):
                return self._get_trigger_url(function_name)
            print(f"FC: Warning - HTTP trigger creation failed for {function_name}: {e}")
            return None

    def _get_trigger_url(self, function_name: str) -> Optional[str]:
        """Get the HTTP trigger URL for an existing function."""
        try:
            response = self.client.get_trigger(function_name, 'http-trigger')
            url = self._extract_trigger_url(response.body)
            if url:
                return url
            print(f"FC: Trigger exists for {function_name} but URL extraction failed")
            return None
        except Exception as e:
            print(f"FC: Error getting trigger URL for {function_name}: {e}")
            return None

    def delete_function(self, name: str) -> Dict[str, Any]:
        """
        Delete an FC function, its triggers, and provision config.

        FC rejects function deletion if provisioned concurrency is still
        configured.  The provision config delete is eventually consistent,
        so we retry the function deletion after a short delay if the first
        attempt gets ProvisionConfigExist.

        Args:
            name: Function name

        Returns:
            Deletion result
        """
        try:
            # Must delete provision config before function
            try:
                self.client.delete_provision_config(
                    name, fc_models.DeleteProvisionConfigRequest(qualifier='LATEST')
                )
            except Exception:
                pass  # Provision config may not exist

            # Must delete triggers before function
            try:
                self.client.delete_trigger(name, 'http-trigger')
            except Exception:
                pass  # Trigger may not exist

            # Try to delete; retry once after delay if provision config
            # deletion hasn't propagated yet
            for attempt in range(3):
                try:
                    self.client.delete_function(name)
                    return {
                        'success': True,
                        'function_name': name,
                        'message': f'Function {name} deleted',
                    }
                except Exception as e:
                    if 'ProvisionConfigExist' in str(e) and attempt < 2:
                        time.sleep(2)
                        continue
                    raise
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }

    def get_function_endpoint(self, name: str) -> Optional[str]:
        """Get the HTTP endpoint URL for a function."""
        return self._get_trigger_url(name)

    # ------------------------------------------------------------------
    # FC Custom Domain management
    # ------------------------------------------------------------------

    def _build_cert_config(self) -> Optional[fc_models.CertConfig]:
        """Build CertConfig from settings, or None if not configured.

        FC requires the private key in traditional PEM format
        (``BEGIN RSA PRIVATE KEY``), not PKCS#8 (``BEGIN PRIVATE KEY``).
        Env vars may use literal ``\\n`` for newlines, so we normalise first.
        """
        settings = self.settings
        if not (settings.fc_wildcard_cert_pem and settings.fc_wildcard_cert_key):
            return None
        cert = settings.fc_wildcard_cert_pem.replace("\\n", "\n")
        key = settings.fc_wildcard_cert_key.replace("\\n", "\n")
        return fc_models.CertConfig(
            cert_name=settings.fc_wildcard_cert_name or "wildcard",
            certificate=cert,
            private_key=key,
        )

    @property
    def fc_cname_target(self) -> str:
        """The CNAME target that FC requires custom domains to resolve to."""
        return f"{self.account_id}.{self.region}.fc.aliyuncs.com"

    def create_or_update_custom_domain(
        self, domain_name: str, function_name: str
    ) -> Dict[str, Any]:
        """
        Create or update an FC custom domain so that *domain_name* routes
        directly to *function_name* over HTTPS (using the wildcard cert).

        On ``CustomDomainAlreadyExists`` the domain is updated instead.

        Prerequisites:
          - DNS CNAME for *domain_name* must already resolve to
            ``{account_id}.{fc_region}.fc.aliyuncs.com``.
          - The private key must be in traditional RSA PEM format.
          - Do NOT pass ``tls_config`` — FC uses sensible defaults.
        """
        cert_config = self._build_cert_config()
        protocol = "HTTPS" if cert_config else "HTTP"

        route_config = fc_models.RouteConfig(
            routes=[
                fc_models.PathConfig(
                    path="/*",
                    function_name=function_name,
                    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                )
            ]
        )

        try:
            create_input = fc_models.CreateCustomDomainInput(
                domain_name=domain_name,
                protocol=protocol,
                cert_config=cert_config,
                route_config=route_config,
            )
            self.client.create_custom_domain(
                fc_models.CreateCustomDomainRequest(body=create_input)
            )
            print(f"FC: Created custom domain {domain_name} -> {function_name}")
            return {"success": True, "domain_name": domain_name}

        except Exception as e:
            if "CustomDomainAlreadyExists" in str(e):
                try:
                    update_input = fc_models.UpdateCustomDomainInput(
                        protocol=protocol,
                        cert_config=cert_config,
                        route_config=route_config,
                    )
                    self.client.update_custom_domain(
                        domain_name,
                        fc_models.UpdateCustomDomainRequest(body=update_input),
                    )
                    print(f"FC: Updated custom domain {domain_name} -> {function_name}")
                    return {"success": True, "domain_name": domain_name}
                except Exception as ue:
                    print(f"FC: Error updating custom domain {domain_name}: {ue}")
                    return {"success": False, "error": str(ue)}

            print(f"FC: Error creating custom domain {domain_name}: {e}")
            return {"success": False, "error": str(e)}

    def delete_custom_domain(self, domain_name: str) -> Dict[str, Any]:
        """Delete an FC custom domain.  Gracefully ignores 'not found'."""
        try:
            self.client.delete_custom_domain(domain_name)
            print(f"FC: Deleted custom domain {domain_name}")
            return {"success": True, "domain_name": domain_name}
        except Exception as e:
            if "CustomDomainNotFound" in str(e) or "404" in str(e):
                return {"success": True, "domain_name": domain_name}
            print(f"FC: Error deleting custom domain {domain_name}: {e}")
            return {"success": False, "error": str(e)}

    def get_custom_domain(self, domain_name: str) -> Optional[Dict[str, Any]]:
        """Return custom domain info, or None if it doesn't exist."""
        try:
            response = self.client.get_custom_domain(domain_name)
            body = response.body
            return {
                "domain_name": getattr(body, "domain_name", domain_name),
                "protocol": getattr(body, "protocol", None),
                "route_config": getattr(body, "route_config", None),
            }
        except Exception:
            return None

    def get_function_status(self, name: str) -> Dict[str, Any]:
        """Get function status and configuration."""
        try:
            response = self.client.get_function(name, fc_models.GetFunctionRequest())
            body = response.body
            endpoint_url = self._get_trigger_url(name)
            return {
                'success': True,
                'function_name': name,
                'state': getattr(body, 'state', 'Unknown'),
                'endpoint_url': endpoint_url,
                'memory_mb': getattr(body, 'memory_size', None),
                'timeout': getattr(body, 'timeout', None),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
            }
