#!/usr/bin/env python3
"""
Deploy edge-routine.js to Aliyun ESA production.

Usage:
  docker exec miaobu-backend python /app/../scripts/deploy-edge-routine.py

Flow:
  1. GetRoutineStagingCodeUploadInfo → get OSS upload credentials
  2. Upload JS code to OSS via multipart POST
  3. CommitRoutineStagingCode → create formal code version
  4. PublishRoutineCodeVersion → deploy to production
"""
import sys
import json
import os
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from app.config import get_settings

ROUTINE_NAME = 'miaobu-router'
CODE_FILE = Path(__file__).parent.parent / 'edge-routine.js'

settings = get_settings()


def esa_request(client, action, params):
    """Make a request to the ESA API."""
    request = CommonRequest()
    request.set_domain(f'esa.{settings.aliyun_region}.aliyuncs.com')
    request.set_protocol_type('https')
    request.set_version('2024-09-10')
    request.set_action_name(action)
    request.set_accept_format('json')
    request.set_method('POST')
    for key, value in params.items():
        request.add_query_param(key, value)
    response = client.do_action_with_exception(request)
    return json.loads(response.decode('utf-8'))


def main():
    # Disable proxy for Aliyun API calls
    for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        os.environ.pop(k, None)

    if not CODE_FILE.exists():
        print(f'Error: {CODE_FILE} not found')
        sys.exit(1)

    code = CODE_FILE.read_text()
    print(f'Code: {CODE_FILE.name} ({len(code)} bytes)')

    client = AcsClient(
        settings.aliyun_access_key_id,
        settings.aliyun_access_key_secret,
        settings.aliyun_region,
    )

    # Step 1: Get upload credentials
    print('\n[1/4] Getting upload credentials...')
    upload_info = esa_request(client, 'GetRoutineStagingCodeUploadInfo', {
        'Name': ROUTINE_NAME,
    })
    oss = upload_info['OssPostConfig']
    print(f'  Key: {oss["key"]}')

    # Step 2: Upload code to OSS
    print('\n[2/4] Uploading code to OSS...')
    form_data = {
        'OSSAccessKeyId': oss['OSSAccessKeyId'],
        'policy': oss['policy'],
        'Signature': oss['Signature'],
        'callback': oss['callback'],
        'x:codeDescription': oss['x:codeDescription'],
        'key': oss['key'],
    }
    if oss.get('XOssSecurityToken'):
        form_data['x-oss-security-token'] = oss['XOssSecurityToken']

    resp = requests.post(
        oss['Url'],
        data=form_data,
        files={'file': ('index.js', code, 'application/javascript')},
    )
    if resp.status_code not in (200, 204):
        print(f'  Upload failed: {resp.status_code} {resp.text[:500]}')
        sys.exit(1)
    print(f'  Upload OK')

    # Step 3: Commit staging code → formal version
    print('\n[3/4] Committing code version...')
    commit = esa_request(client, 'CommitRoutineStagingCode', {
        'Name': ROUTINE_NAME,
        'CodeDescription': 'deploy via script',
    })
    code_version = commit.get('CodeVersion')
    if not code_version:
        print(f'  Commit failed: {json.dumps(commit)}')
        sys.exit(1)
    print(f'  Version: {code_version}')

    # Step 4: Publish to production
    print('\n[4/4] Publishing to production...')
    esa_request(client, 'PublishRoutineCodeVersion', {
        'Name': ROUTINE_NAME,
        'Env': 'production',
        'CodeVersion': code_version,
    })
    print(f'  Published!')

    print(f'\nDone. {ROUTINE_NAME} v{code_version} is live.')


if __name__ == '__main__':
    main()
