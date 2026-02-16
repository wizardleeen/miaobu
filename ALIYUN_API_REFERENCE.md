# Aliyun API Reference for Miaobu

This document lists all Aliyun APIs used in the Miaobu project, with examples and usage patterns for future reference.

## Table of Contents
- [ESA (Edge Security Acceleration) APIs](#esa-apis)
- [Edge KV APIs](#edge-kv-apis)
- [API Authentication](#api-authentication)
- [Common Patterns](#common-patterns)

---

## ESA APIs

### Authentication & Configuration

```python
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import json

# Initialize client
client = AcsClient(
    access_key_id=ESA_ACCESS_KEY_ID,
    access_key_secret=ESA_ACCESS_KEY_SECRET,
    region_id='cn-hangzhou'  # ESA uses cn-hangzhou region
)

# Common request setup
request = CommonRequest()
request.set_accept_format('json')
request.set_domain('esa.cn-hangzhou.aliyuncs.com')
request.set_method('POST')
request.set_protocol_type('https')
request.set_version('2024-09-10')  # ESA API version
```

### 1. CreateCustomHostname

**Purpose:** Create a custom hostname (domain) on ESA site.

**Parameters:**
- `SiteId` (required): ESA site ID
- `Hostname` (required): The custom domain (e.g., "example.com")
- `RecordId` (required): CNAME record ID for routing
- `SslFlag` (optional): "on" or "off" for SSL
- `CertType` (optional): "free" for automatic Let's Encrypt certificate

**Example:**
```python
params = {
    'SiteId': 1127768632068624,
    'Hostname': 'kyvy.me',
    'RecordId': 4513850898327424,
    'SslFlag': 'on',
    'CertType': 'free'
}
result = _make_request('CreateCustomHostname', params)
# Returns: {'HostnameId': '4514973387335744', ...}
```

**Response Fields:**
- `HostnameId`: Unique ID for the custom hostname
- `Status`: 'pending', 'active', 'offline'
- `VerifyCode`: Verification token for TXT record
- `VerifyHost`: Host for TXT record (e.g., "_esa_custom_hostname.example.com")

**Implementation:** `backend/app/services/esa.py::create_custom_hostname()`

---

### 2. GetCustomHostname

**Purpose:** Get detailed status of a custom hostname, including SSL and ICP status.

**Parameters:**
- `SiteId` (required): ESA site ID
- `HostnameId` (required): Custom hostname ID from CreateCustomHostname

**Example:**
```python
params = {
    'SiteId': 1127768632068624,
    'HostnameId': '4514973387335744'
}
result = _make_request('GetCustomHostname', params)
```

**Response Fields:**
- `Hostname`: The domain name
- `Status`: 'pending', 'active', 'offline'
- `OfflineReason`: If status is offline:
  - `'missing_icp'`: Domain needs ICP filing
  - Other reasons may include DNS issues
- `CertStatus`: 'OK', 'ApplyFailed', 'Pending'
- `CertNotAfter`: SSL certificate expiration date
- `VerifyCode`: Verification token
- `SslFlag`: 'on' or 'off'

**ICP Detection Pattern:**
```python
model = result['data'].get('CustomHostnameModel', {})
if model.get('OfflineReason') == 'missing_icp':
    # Domain requires ICP filing
    # Show user: https://beian.aliyun.com
```

**Implementation:** `backend/app/services/esa.py::get_custom_hostname_status()`

---

### 3. ListCustomHostnames

**Purpose:** List all custom hostnames for an ESA site.

**Parameters:**
- `SiteId` (required): ESA site ID
- `PageSize` (optional): Default 500
- `PageNumber` (optional): Default 1

**Example:**
```python
params = {'SiteId': 1127768632068624}
result = _make_request('ListCustomHostnames', params)
```

**Response Structure:**
```json
{
  "TotalCount": 3,
  "PageSize": 500,
  "PageNumber": 1,
  "Hostnames": [
    {
      "HostnameId": "4514973387335744",
      "Hostname": "kyvy.me",
      "Status": "active",
      "OfflineReason": "",
      "CertStatus": "OK",
      "CertNotAfter": "2026-05-17T10:29:50Z",
      "VerifyCode": "verify_9e72a5cbb7d2b47216d39843eaa931ef",
      "RecordName": "cname.metavm.tech"
    }
  ]
}
```

**Implementation:** Used in debugging and manual scripts

---

### 4. VerifyCustomHostname

**Purpose:** Trigger verification check for custom hostname after DNS is configured.

**Parameters:**
- `SiteId` (required): ESA site ID
- `HostnameId` (required): Custom hostname ID

**Example:**
```python
params = {
    'SiteId': 1127768632068624,
    'HostnameId': '4514973387335744'
}
result = _make_request('VerifyCustomHostname', params)
```

**Verification Process:**
1. User adds TXT record: `_esa_custom_hostname.example.com` → verification token
2. User adds CNAME record: `example.com` → `cname.metavm.tech`
3. Call VerifyCustomHostname API
4. ESA checks DNS records
5. If verified, status changes to 'active' and SSL provisioning begins

**Error Handling:**
- If verification fails, check DNS with `GetCustomHostname`
- Common errors: "InvalidICP", "DNS not found", "TXT record mismatch"

**Implementation:** `backend/app/api/v1/domains_esa.py::verify_custom_domain()`

---

### 5. DeleteCustomHostname

**Purpose:** Remove a custom hostname from ESA.

**Parameters:**
- `SiteId` (required): ESA site ID
- `HostnameId` (required): Custom hostname ID to delete

**Example:**
```python
params = {
    'SiteId': 1127768632068624,
    'HostnameId': '4514973387335744'
}
result = _make_request('DeleteCustomHostname', params)
```

**Note:** This only removes from ESA. You must also:
1. Delete from database (`custom_domains` table)
2. Remove Edge KV mapping (see Edge KV section)

**Implementation:** `backend/app/services/esa.py::delete_custom_hostname()`

---

## Edge KV APIs

Edge KV is used to map custom domains to OSS paths at the edge for routing.

### Configuration

```python
# Edge KV uses the same ESA client
ESA_EDGE_KV_NAMESPACE_ID = '961854465965670400'  # miaobu namespace
```

### 1. PutEdgeKVKey

**Purpose:** Store domain-to-deployment mapping at the edge.

**Parameters:**
- `Namespace` (required): Edge KV namespace name (e.g., "miaobu")
- `Key` (required): The custom domain (e.g., "example.com")
- `Value` (required): JSON string with mapping data

**Mapping Value Structure:**
```json
{
  "oss_path": "projects/1/deployments/42",
  "domain_id": 12,
  "deployment_id": 42,
  "project_id": 1,
  "updated_at": "2026-02-16T12:50:00Z"
}
```

**Example:**
```python
mapping = {
    'oss_path': f'projects/{project_id}/deployments/{deployment_id}',
    'domain_id': domain.id,
    'deployment_id': deployment_id,
    'project_id': project_id,
    'updated_at': datetime.utcnow().isoformat()
}

params = {
    'Namespace': 'miaobu',
    'Key': 'example.com',
    'Value': json.dumps(mapping)
}
result = _make_request('PutEdgeKVKey', params)
```

**Important:** Edge KV sync can take 10-30 seconds to propagate globally.

**Implementation:** `backend/app/services/esa.py::sync_edge_kv()`

---

### 2. GetEdgeKVKey

**Purpose:** Retrieve current Edge KV mapping for a domain.

**Parameters:**
- `Namespace` (required): Edge KV namespace name
- `Key` (required): The domain to look up

**Example:**
```python
params = {
    'Namespace': 'miaobu',
    'Key': 'example.com'
}
result = _make_request('GetEdgeKVKey', params)
value = json.loads(result['data']['Value'])
# value = {'oss_path': 'projects/1/deployments/42', ...}
```

**Used For:**
- Verifying Edge KV sync status
- Debugging routing issues
- Checking current deployment for a domain

**Implementation:** `backend/app/services/esa.py::get_edge_kv()`

---

### 3. DeleteEdgeKVKey

**Purpose:** Remove Edge KV mapping for a domain.

**Parameters:**
- `Namespace` (required): Edge KV namespace name
- `Key` (required): The domain to delete

**Example:**
```python
params = {
    'Namespace': 'miaobu',
    'Key': 'example.com'
}
result = _make_request('DeleteEdgeKVKey', params)
```

**When to Use:**
- When deleting a custom domain completely
- When moving domain to a different project

**Implementation:** `backend/app/services/esa.py::delete_edge_kv()`

---

## Edge Routine APIs

Edge Routines are JavaScript functions that run at the edge for URL rewriting.

### Current Status

**Routing Logic Location:** `edge-routine-aliyun-correct.js`

**Edge Routine Process:**
1. Request comes to custom domain (e.g., kyvy.me)
2. Edge Routine looks up domain in Edge KV
3. Gets `oss_path` from Edge KV value
4. Rewrites URL to OSS: `https://miaobu-deployments.oss-cn-hangzhou.aliyuncs.com/{oss_path}/index.html`
5. Removes `Content-Disposition` header to prevent downloads
6. Returns response to user

### Key Edge Routine Code Snippet

```javascript
// Initialize EdgeKV (Aliyun ESA way, not Cloudflare)
const edgeKV = new EdgeKV({ namespace: "miaobu" });

// Get mapping
const kvValue = await edgeKV.get(hostname, { type: "text" });
const mapping = JSON.parse(kvValue);

// Build OSS URL
let ossPath = `/${mapping.oss_path}${url.pathname}`;
if (ossPath.endsWith('/')) {
  ossPath = `${ossPath}index.html`;
}

const ossUrl = `https://miaobu-deployments.oss-cn-hangzhou.aliyuncs.com${ossPath}`;

// Remove Content-Disposition header to prevent downloads
const headers = new Headers(ossResponse.headers);
headers.delete('Content-Disposition');
headers.delete('content-disposition');
```

### Edge Routine Deployment APIs (Attempted)

**Note:** These APIs were explored but a working upload/deployment flow was not established during the session.

**APIs Attempted:**
- `UploadRoutineCode` - Not found in API
- `CreateRoutineCodeVersion` - Not found
- `UpdateRoutineCode` - Not found
- `CommitRoutineStagingCode` - Found but requires code to be uploaded first
- `CreateRoutineCodeDeployment` - Mentioned in docs

**Current Deployment Method:**
- Manual deployment via Aliyun ESA Console
- Or use `upload_routine.py` script (requires debugging)

**Script Location:** `upload_routine.py`

```python
# Current attempt (needs correct API discovery)
encoded_code = base64.b64encode(code.encode('utf-8')).decode('utf-8')
params = {
    'Name': 'miaobu-router',
    'CodeDescription': 'Fix Content-Disposition header',
    'Code': encoded_code,
}
result = esa._make_request('UploadRoutineCode', params)
```

---

## API Authentication

### ESA Service Class Pattern

All ESA APIs use this common pattern:

```python
class ESAService:
    def __init__(self):
        self.access_key_id = settings.ESA_ACCESS_KEY_ID
        self.access_key_secret = settings.ESA_ACCESS_KEY_SECRET
        self.site_id = settings.ESA_SITE_ID
        self.edge_kv_namespace = settings.ESA_EDGE_KV_NAMESPACE
        self.client = AcsClient(
            self.access_key_id,
            self.access_key_secret,
            'cn-hangzhou'
        )

    def _make_request(self, action: str, params: Dict) -> Dict:
        """Generic ESA API request handler."""
        request = CommonRequest()
        request.set_accept_format('json')
        request.set_domain('esa.cn-hangzhou.aliyuncs.com')
        request.set_method('POST')
        request.set_protocol_type('https')
        request.set_version('2024-09-10')
        request.set_action_name(action)

        for key, value in params.items():
            request.add_query_param(key, str(value))

        response = self.client.do_action_with_exception(request)
        data = json.loads(response)

        print(f"ESA API Response - Action: {action}, Result: {data}")

        return {
            'success': True,
            'data': data
        }
```

---

## Common Patterns

### Pattern 1: Create Domain with Verification

```python
# Step 1: Create custom hostname
create_result = esa.create_custom_hostname(
    hostname='example.com',
    record_id=CNAME_RECORD_ID,
    ssl_enabled=True,
    cert_type='free'
)

hostname_id = create_result['hostname_id']
verify_token = create_result['verify_token']
verify_host = create_result['verify_host']

# Step 2: User adds DNS records
# TXT: _esa_custom_hostname.example.com -> verify_token
# CNAME: example.com -> cname.metavm.tech

# Step 3: Verify domain
verify_result = esa.verify_custom_hostname(hostname_id)

# Step 4: Check status (including ICP)
status = esa.get_custom_hostname_status(hostname_id)
if status['icp_required']:
    return {'error': 'ICP filing required', 'url': 'https://beian.aliyun.com'}
```

### Pattern 2: Promote Deployment to Domain

```python
# Step 1: Update Edge KV mapping
mapping = {
    'oss_path': f'projects/{project_id}/deployments/{deployment_id}',
    'domain_id': domain.id,
    'deployment_id': deployment_id,
    'project_id': project_id
}

esa.sync_edge_kv(domain='example.com', mapping=mapping)

# Step 2: Mark as synced in database
domain.edge_kv_synced = True
domain.active_deployment_id = deployment_id
db.commit()

# Step 3: Wait 10-30 seconds for global propagation
# Edge Routine will now route to new deployment
```

### Pattern 3: ICP Detection

```python
# After domain verification
status = esa.get_custom_hostname_status(hostname_id)

if status.get('offline_reason') == 'missing_icp':
    return {
        'icp_required': True,
        'message': 'Domain requires ICP filing for mainland China',
        'filing_url': 'https://beian.aliyun.com',
        'note': 'Domain will remain offline until ICP filing is completed'
    }
```

### Pattern 4: Error Handling

```python
try:
    result = esa._make_request(action, params)
    return {'success': True, 'data': result['data']}
except Exception as e:
    error_msg = str(e)

    # ICP-related errors
    if 'InvalidICP' in error_msg or 'ICP filing' in error_msg:
        return {
            'success': False,
            'error': 'ICP filing required',
            'icp_required': True
        }

    # Generic error
    return {'success': False, 'error': error_msg}
```

---

## Configuration Reference

### Environment Variables

```bash
# ESA Configuration
ESA_ACCESS_KEY_ID=your_access_key_id
ESA_ACCESS_KEY_SECRET=your_access_key_secret
ESA_SITE_ID=1127768632068624
ESA_SITE_NAME=metavm.tech
ESA_EDGE_KV_NAMESPACE=miaobu
ESA_EDGE_KV_NAMESPACE_ID=961854465965670400

# CNAME Record (for custom hostnames)
ESA_CNAME_RECORD_ID=4513850898327424
ESA_CNAME_TARGET=cname.metavm.tech

# Edge Routine
ESA_EDGE_ROUTINE_NAME=miaobu-router
ESA_EDGE_ROUTINE_VERSION=1771236256032919391
```

### Key Resources

- **ESA Site ID:** 1127768632068624
- **Site Name:** metavm.tech
- **Edge KV Namespace:** miaobu (ID: 961854465965670400)
- **CNAME Record ID:** 4513850898327424
- **CNAME Target:** cname.metavm.tech
- **Edge Routine:** miaobu-router

### OSS Configuration

```bash
# OSS Bucket for deployments
OSS_BUCKET_NAME=miaobu-deployments
OSS_REGION=oss-cn-hangzhou
OSS_ORIGIN=miaobu-deployments.oss-cn-hangzhou.aliyuncs.com

# OSS Path Structure
# Format: projects/{project_id}/deployments/{deployment_id}/
# Example: projects/1/deployments/42/index.html
```

---

## API Documentation Links

- **ESA API Reference:** https://help.aliyun.com/zh/edge-security-acceleration/esa/
- **Edge KV Documentation:** https://help.aliyun.com/zh/edge-security-acceleration/esa/user-guide/edge-kv
- **ICP Filing:** https://beian.aliyun.com

---

## Troubleshooting

### Issue: Domain shows "offline" status

**Check:**
1. DNS records configured correctly (TXT + CNAME)
2. Call `GetCustomHostname` to check `OfflineReason`
3. If `missing_icp`, domain needs ICP filing
4. If DNS issue, verify CNAME points to correct target

### Issue: Content downloads instead of displaying

**Cause:** OSS returns `Content-Disposition: attachment` header

**Solution:** Edge Routine removes this header (lines 53-56 in edge-routine-aliyun-correct.js)

### Issue: Domain routes to wrong deployment

**Check:**
1. Verify Edge KV mapping: Call `GetEdgeKVKey`
2. Check `oss_path` in mapping
3. Ensure `edge_kv_synced` is true in database
4. Wait 10-30 seconds after sync for propagation

### Issue: SSL certificate not provisioning

**Check:**
1. Domain must be verified first
2. Check `CertStatus` in `GetCustomHostname`
3. If `ApplyFailed`, check `CertApplyMessage`
4. Ensure DNS is publicly resolvable

---

## Session Summary

This session completed:
- ✅ ESA custom hostname management
- ✅ Edge KV synchronization for domain routing
- ✅ ICP filing detection and user guidance
- ✅ Automatic SSL provisioning via ESA
- ✅ Content-Disposition header fix in Edge Routine
- ✅ Domain list API endpoint
- ✅ Form submission bug fix (type="button")
- ⚠️  Edge Routine upload API (needs further investigation)

**Tested Domains:**
- kyvi.me (no ICP, status: offline)
- kyvy.me (has ICP, status: active, SSL: OK)
- foo.metavm.tech (internal domain, status: active)

**Files Updated:**
- `backend/app/services/esa.py` - ESA service integration
- `backend/app/api/v1/domains_esa.py` - Domains API
- `frontend/src/components/DomainsManagement.tsx` - UI improvements
- `edge-routine-aliyun-correct.js` - Edge routing logic
