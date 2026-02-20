#!/usr/bin/env python3
"""
Provision Aliyun resources for Miaobu staging environment at kyvy.me.

Usage:
  cd /path/to/miaobu && PYTHONPATH=backend python scripts/setup-staging-infra.py

This script is idempotent — it skips resources that already exist.

Resources created:
  1. OSS bucket: kyvy-deployments (cn-hangzhou, public-read)
  2. OSS bucket: kyvy-deployments-qingdao (cn-qingdao, for FC code packages)
  3. ESA site: kyvy.me
  4. Edge KV namespace: kyvy (on the new ESA site)
  5. Edge routine: kyvy-router (deployed to the new ESA site)
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

import oss2
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from app.config import get_settings

settings = get_settings()

# Target configuration
STAGING_DOMAIN = "kyvy.me"
KV_NAMESPACE_NAME = "kyvy"
ROUTINE_NAME = "kyvy-router"
STATIC_BUCKET_NAME = "kyvy-deployments"
STATIC_BUCKET_REGION = "cn-hangzhou"
FC_BUCKET_NAME = "kyvy-deployments-qingdao"
FC_BUCKET_REGION = "cn-qingdao"

CODE_FILE = Path(__file__).parent.parent / 'edge-routine.js'


def disable_proxy():
    """Remove proxy env vars for direct Aliyun API access."""
    for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        os.environ.pop(k, None)


def make_esa_request(client, action, params, method='POST'):
    """Make a request to the ESA API."""
    request = CommonRequest()
    request.set_domain(f'esa.{settings.aliyun_region}.aliyuncs.com')
    request.set_protocol_type('https')
    request.set_version('2024-09-10')
    request.set_action_name(action)
    request.set_accept_format('json')
    request.set_method(method)
    for key, value in params.items():
        request.add_query_param(key, value)
    response = client.do_action_with_exception(request)
    return json.loads(response.decode('utf-8'))


def create_oss_bucket(bucket_name, region, acl='private'):
    """Create an OSS bucket if it doesn't exist."""
    endpoint = f'oss-{region}.aliyuncs.com'
    auth = oss2.Auth(settings.aliyun_access_key_id, settings.aliyun_access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)

    try:
        bucket.get_bucket_info()
        print(f'  [skip] Bucket {bucket_name} already exists')
        return True
    except oss2.exceptions.NoSuchBucket:
        pass

    try:
        bucket.create_bucket(acl)
        print(f'  [created] Bucket {bucket_name} in {region} (ACL: {acl})')
        return True
    except Exception as e:
        print(f'  [error] Failed to create bucket {bucket_name}: {e}')
        return False


def main():
    disable_proxy()

    print('=' * 60)
    print('Miaobu Staging Infrastructure Provisioning')
    print(f'Target domain: {STAGING_DOMAIN}')
    print('=' * 60)

    client = AcsClient(
        settings.aliyun_access_key_id,
        settings.aliyun_access_key_secret,
        settings.aliyun_region,
    )

    results = {}

    # --- Step 1: Create OSS buckets ---
    print('\n[1/5] Creating OSS buckets...')
    create_oss_bucket(STATIC_BUCKET_NAME, STATIC_BUCKET_REGION, acl=oss2.BUCKET_ACL_PUBLIC_READ)
    create_oss_bucket(FC_BUCKET_NAME, FC_BUCKET_REGION)

    # --- Step 2: Create ESA site ---
    print('\n[2/5] Creating ESA site...')
    try:
        site_result = make_esa_request(client, 'CreateSite', {
            'SiteName': STAGING_DOMAIN,
            'Coverage': 'domestic',
            'AccessType': 'NS',
        })
        site_id = str(site_result.get('SiteId', ''))
        results['site_id'] = site_id
        print(f'  [created] ESA site: {STAGING_DOMAIN} (SiteId: {site_id})')

        # Get nameservers
        ns = site_result.get('NameServerList', '')
        if ns:
            print(f'  Nameservers: {ns}')
            results['nameservers'] = ns

    except Exception as e:
        error_msg = str(e)
        if 'SiteAlreadyExist' in error_msg or 'already exist' in error_msg.lower():
            print(f'  [skip] ESA site {STAGING_DOMAIN} already exists')
            # Try to get existing site ID
            try:
                list_result = make_esa_request(client, 'ListSites', {
                    'SiteName': STAGING_DOMAIN,
                })
                sites = list_result.get('Sites', [])
                if sites:
                    site_id = str(sites[0].get('SiteId', ''))
                    results['site_id'] = site_id
                    print(f'  Existing SiteId: {site_id}')
            except Exception as e2:
                print(f'  [warning] Could not retrieve existing site ID: {e2}')
        else:
            print(f'  [error] Failed to create ESA site: {e}')

    # --- Step 3: Create Edge KV namespace ---
    print('\n[3/5] Creating Edge KV namespace...')
    if 'site_id' not in results:
        print('  [skip] Cannot create KV namespace without site ID')
    else:
        try:
            kv_result = make_esa_request(client, 'CreateKvNamespace', {
                'Namespace': KV_NAMESPACE_NAME,
            })
            namespace_id = str(kv_result.get('NamespaceId', kv_result.get('Namespace', {}).get('NamespaceId', '')))
            results['kv_namespace_id'] = namespace_id
            print(f'  [created] Edge KV namespace: {KV_NAMESPACE_NAME} (ID: {namespace_id})')
        except Exception as e:
            error_msg = str(e)
            if 'AlreadyExist' in error_msg or 'already exist' in error_msg.lower():
                print(f'  [skip] Edge KV namespace {KV_NAMESPACE_NAME} already exists')
                # Try to list namespaces to get the ID
                try:
                    list_result = make_esa_request(client, 'ListKvNamespaces', {})
                    for ns in list_result.get('Namespaces', []):
                        if ns.get('Namespace') == KV_NAMESPACE_NAME:
                            namespace_id = str(ns.get('NamespaceId', ''))
                            results['kv_namespace_id'] = namespace_id
                            print(f'  Existing NamespaceId: {namespace_id}')
                            break
                except Exception as e2:
                    print(f'  [warning] Could not retrieve existing namespace ID: {e2}')
            else:
                print(f'  [error] Failed to create KV namespace: {e}')

    # --- Step 4: Deploy edge routine ---
    print('\n[4/5] Deploying edge routine...')
    if not CODE_FILE.exists():
        print(f'  [error] {CODE_FILE} not found')
    else:
        raw_code = CODE_FILE.read_text()
        # Template-replace placeholders
        code = raw_code.replace('__BASE_DOMAIN__', STAGING_DOMAIN)
        code = code.replace('__KV_NAMESPACE__', KV_NAMESPACE_NAME)
        print(f'  Code: {CODE_FILE.name} ({len(code)} bytes)')

        try:
            # Create the routine first (may already exist)
            try:
                make_esa_request(client, 'CreateRoutine', {
                    'Name': ROUTINE_NAME,
                    'Description': f'Edge router for {STAGING_DOMAIN}',
                    'SpecName': 'edge_routine',
                })
                print(f'  [created] Routine: {ROUTINE_NAME}')
            except Exception as e:
                if 'AlreadyExist' in str(e) or 'already exist' in str(e).lower():
                    print(f'  [skip] Routine {ROUTINE_NAME} already exists')
                else:
                    print(f'  [warning] CreateRoutine: {e}')

            # Get upload credentials
            upload_info = make_esa_request(client, 'GetRoutineStagingCodeUploadInfo', {
                'Name': ROUTINE_NAME,
            })
            oss_config = upload_info['OssPostConfig']

            # Upload code to OSS
            form_data = {
                'OSSAccessKeyId': oss_config['OSSAccessKeyId'],
                'policy': oss_config['policy'],
                'Signature': oss_config['Signature'],
                'callback': oss_config['callback'],
                'x:codeDescription': oss_config['x:codeDescription'],
                'key': oss_config['key'],
            }
            if oss_config.get('XOssSecurityToken'):
                form_data['x-oss-security-token'] = oss_config['XOssSecurityToken']

            resp = requests.post(
                oss_config['Url'],
                data=form_data,
                files={'file': ('index.js', code, 'application/javascript')},
            )
            if resp.status_code not in (200, 204):
                print(f'  [error] Upload failed: {resp.status_code} {resp.text[:500]}')
            else:
                print(f'  [uploaded] Code to OSS')

                # Commit staging code
                commit = make_esa_request(client, 'CommitRoutineStagingCode', {
                    'Name': ROUTINE_NAME,
                    'CodeDescription': 'initial staging deploy',
                })
                code_version = commit.get('CodeVersion')
                if code_version:
                    print(f'  [committed] Version: {code_version}')

                    # Publish
                    make_esa_request(client, 'PublishRoutineCodeVersion', {
                        'Name': ROUTINE_NAME,
                        'Env': 'production',
                        'CodeVersion': code_version,
                    })
                    print(f'  [published] {ROUTINE_NAME} v{code_version}')
                else:
                    print(f'  [error] Commit failed: {json.dumps(commit)}')

        except Exception as e:
            print(f'  [error] Edge routine deployment failed: {e}')

    # --- Step 5: Print results ---
    print('\n[5/5] Results summary')
    print('=' * 60)
    print('\nResource IDs for .env.staging:')
    print(f'  ALIYUN_ESA_SITE_ID={results.get("site_id", "<not available>")}')
    print(f'  ALIYUN_ESA_SITE_NAME={STAGING_DOMAIN}')
    print(f'  ALIYUN_ESA_EDGE_KV_NAMESPACE_ID={results.get("kv_namespace_id", "<not available>")}')
    print(f'  ALIYUN_ESA_EDGE_KV_NAMESPACE={KV_NAMESPACE_NAME}')
    print(f'  ALIYUN_OSS_BUCKET={STATIC_BUCKET_NAME}')
    print(f'  ALIYUN_FC_OSS_BUCKET={FC_BUCKET_NAME}')
    print(f'  FC_FUNCTION_PREFIX=kyvy')
    print(f'  CDN_BASE_DOMAIN={STAGING_DOMAIN}')

    if results.get('nameservers'):
        print(f'\nDNS Configuration:')
        print(f'  Set {STAGING_DOMAIN} NS records to: {results["nameservers"]}')

    print('\nManual steps:')
    print('  1. Configure DNS NS records for kyvy.me to point to ESA nameservers')
    print('  2. Create a new GitHub OAuth App with callback: https://api.kyvy.me/api/v1/auth/github/callback')
    print('  3. Add MIAOBU_CALLBACK_SECRET_STAGING to GitHub repo secrets')
    print('  4. Create miaobu_staging database and run migrations')
    print('  5. Fill in .env.staging with generated secrets and resource IDs')
    print('  6. Deploy backend and frontend for staging')


if __name__ == '__main__':
    main()
