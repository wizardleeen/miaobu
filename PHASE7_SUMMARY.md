# Phase 7: Custom Domains - COMPLETED ✅

## Overview

Phase 7 implements complete custom domain support with DNS verification. Users can now add their own domains (like `www.mysite.com`) instead of only using the default `{slug}.miaobu.app` subdomain. The system automatically guides users through DNS configuration and verifies domain ownership before enabling the domain.

## Features Implemented

### 1. DNS Verification Service (`backend/app/services/dns.py`)

**Complete DNS Management:**

#### TXT Record Verification:
- **Generate Verification Tokens:**
  - Creates unique verification tokens for each domain
  - Format: `miaobu-verification={random-token}`
  - URL-safe tokens using `secrets.token_urlsafe(32)`

- **Verify TXT Records:**
  - Checks for verification token in DNS TXT records
  - Supports subdomain verification (` _miaobu-verification.domain.com`)
  - Handles DNS timeouts and failures gracefully
  - Returns detailed verification status

```python
# Generate token
token = DNSService.generate_verification_token()
# Output: "miaobu-verification=abc123xyz..."

# Verify domain
result = DNSService.verify_txt_record("example.com", token)
# Returns: {"success": True, "verified": True, "message": "..."}
```

#### CNAME Record Verification:
- Verifies CNAME points to CDN domain
- Handles apex domains (which can't use CNAME)
- Suggests A record for apex domains
- Returns current DNS configuration

#### Comprehensive DNS Status:
- Checks A, CNAME, and TXT records
- Returns complete DNS configuration
- Identifies record types present
- Helps troubleshoot DNS issues

#### Domain Utilities:
- Extract root domain from subdomains
- Detect apex vs subdomain
- Helpful for DNS configuration logic

### 2. CDN Domain Binding (`backend/app/services/cdn.py`)

**Extended CDN Service:**

#### Add Custom Domain to CDN:
```python
def add_custom_domain(domain_name, source_type="oss", source_content=None):
    # Adds domain to Alibaba Cloud CDN
    # Configures origin server (OSS bucket)
    # Returns CNAME for DNS configuration
```

**Features:**
- Automatic OSS bucket as origin
- Download/distribution CDN type
- Error handling for duplicate domains
- Domain registration verification

#### Remove Custom Domain:
```python
def delete_custom_domain(domain_name):
    # Removes domain from CDN
    # Cleans up CDN configuration
```

#### Enable/Disable Domains:
```python
def enable_custom_domain(domain_name):
    # Starts CDN service for domain

def disable_custom_domain(domain_name):
    # Stops CDN service (keeps configuration)
```

### 3. Custom Domains API (`backend/app/api/v1/domains.py`)

**Complete CRUD Operations:**

#### Create Custom Domain:
```http
POST /api/v1/domains
{
  "project_id": 5,
  "domain": "www.example.com"
}

Response:
{
  "id": 1,
  "project_id": 5,
  "domain": "www.example.com",
  "is_verified": false,
  "verification_token": "miaobu-verification=abc123...",
  "ssl_status": "pending"
}
```

#### List Domains:
```http
GET /api/v1/domains?project_id=5

Response: [
  {
    "id": 1,
    "domain": "www.example.com",
    "is_verified": true,
    "verified_at": "2024-02-15T10:30:00Z"
  }
]
```

#### Verify Domain:
```http
POST /api/v1/domains/1/verify

Response:
{
  "success": true,
  "verified": true,
  "message": "Domain verified successfully",
  "cdn_status": "Domain added to CDN"
}
```

#### Check DNS Status:
```http
POST /api/v1/domains/1/check-dns

Response:
{
  "success": true,
  "domain": "www.example.com",
  "is_verified": true,
  "dns_status": {
    "has_a_record": false,
    "has_cname_record": true,
    "has_txt_record": true
  },
  "txt_verification": {
    "verified": true
  }
}
```

#### Get DNS Instructions:
```http
GET /api/v1/domains/1/dns-instructions

Response:
{
  "domain": "www.example.com",
  "is_apex": false,
  "steps": [
    {
      "step": 1,
      "title": "Add DNS TXT Record for Verification",
      "record_type": "TXT",
      "name": "_miaobu-verification.www.example.com",
      "value": "miaobu-verification=abc123...",
      "ttl": 300
    },
    {
      "step": 2,
      "title": "Add DNS CNAME Record",
      "record_type": "CNAME",
      "name": "www.example.com",
      "value": "cdn.miaobu.app",
      "ttl": 3600
    }
  ]
}
```

#### Delete Domain:
```http
DELETE /api/v1/domains/1

Response: 204 No Content
```

### 4. Frontend Domain Management (`frontend/src/components/DomainsManagement.tsx`)

**Complete UI Component:**

#### Domain List View:
- Shows all custom domains for project
- Verification status badges (✓ Verified / ⏳ Pending)
- Add domain button
- Per-domain actions (Setup DNS, Delete)

#### Add Domain Modal:
- Simple form to add new domain
- Domain validation
- Creates domain with verification token

#### DNS Configuration Modal:
- Step-by-step DNS instructions
- Copy-paste ready DNS records
- Current DNS status display
- Real-time verification check
- Verify domain button

**DNS Instructions Display:**
```
┌─────────────────────────────────────────────┐
│ DNS Configuration: www.example.com          │
├─────────────────────────────────────────────┤
│ ⏳ Verification Pending                     │
│ Please configure DNS records below          │
├─────────────────────────────────────────────┤
│                                             │
│ Step 1: Add DNS TXT Record                  │
│ Type: TXT                                   │
│ Name: _miaobu-verification.www.example.com  │
│ Value: miaobu-verification=abc123...        │
│ TTL: 300                                    │
│                                             │
│ Step 2: Add DNS CNAME Record                │
│ Type: CNAME                                 │
│ Name: www.example.com                       │
│ Value: cdn.miaobu.app                       │
│ TTL: 3600                                   │
│                                             │
│ [🔄 Check DNS]  [✓ Verify Domain]  [Close] │
└─────────────────────────────────────────────┘
```

#### DNS Status Display:
- Domain exists status
- Has TXT record
- Has CNAME record
- Verification status
- Helpful error messages

### 5. Project Settings Integration

**Added to ProjectSettingsPage:**
- Custom Domains section
- Full DomainsManagement component
- Located between Git Settings and Save Button
- Seamlessly integrated into project settings flow

## Architecture

### Domain Verification Flow

```
1. User adds custom domain
   ↓
2. System generates verification token
   ↓
3. User adds TXT record to DNS
   _miaobu-verification.domain.com → miaobu-verification=token
   ↓
4. User clicks "Verify Domain"
   ↓
5. System queries DNS for TXT record
   ↓
6. If token matches → Domain verified ✓
   ↓
7. System adds domain to CDN
   ↓
8. User adds CNAME record to DNS
   domain.com → cdn.miaobu.app
   ↓
9. Domain is live! 🎉
```

### DNS Record Strategy

**For Subdomains (www.example.com):**
```
# Verification
_miaobu-verification.www.example.com  300  IN  TXT  "miaobu-verification=abc123..."

# CDN Routing
www.example.com  3600  IN  CNAME  cdn.miaobu.app
```

**For Apex Domains (example.com):**
```
# Verification
_miaobu-verification.example.com  300  IN  TXT  "miaobu-verification=abc123..."

# CDN Routing (A record required)
example.com  3600  IN  A  <CDN-IP-Address>
```

Note: Apex domains cannot use CNAME records. They require A records with CDN IP address.

### Database Schema

**CustomDomain Model (existing):**
```python
class CustomDomain(Base):
    __tablename__ = "custom_domains"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))

    # Domain info
    domain = Column(String(255), unique=True)  # www.example.com
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String(255))   # miaobu-verification=...

    # SSL info (Phase 8)
    ssl_status = Column(Enum(SSLStatus), default=SSLStatus.PENDING)
    ssl_certificate_id = Column(String(255))
    ssl_expires_at = Column(DateTime)

    created_at = Column(DateTime)
    verified_at = Column(DateTime)
```

## File Structure

**New Files:**
```
backend/app/services/dns.py           (280 lines)
backend/app/api/v1/domains.py         (380 lines)
frontend/src/components/DomainsManagement.tsx  (410 lines)
```

**Modified Files:**
```
backend/app/main.py                   (added domains router)
backend/app/services/cdn.py           (added domain management methods)
backend/requirements.txt              (added dnspython==2.4.2)
frontend/src/services/api.ts          (added domain API methods)
frontend/src/pages/ProjectSettingsPage.tsx  (integrated DomainsManagement)
```

## Configuration

### Environment Variables

No new environment variables required! Uses existing:
```bash
# Already configured
ALIYUN_ACCESS_KEY_ID=<your-key>
ALIYUN_ACCESS_KEY_SECRET=<your-secret>
ALIYUN_CDN_DOMAIN=cdn.miaobu.app
```

### DNS Provider Support

Works with all DNS providers:
- ✅ Cloudflare
- ✅ Namecheap
- ✅ GoDaddy
- ✅ Alibaba Cloud DNS
- ✅ Route53 (AWS)
- ✅ Google Cloud DNS
- ✅ Any DNS provider that supports TXT and CNAME records

## Usage Examples

### Add Custom Domain

**1. Navigate to Project Settings:**
```
Projects → Select Project → Settings → Custom Domains
```

**2. Click "Add Domain":**
```
Enter: www.mysite.com
Click: Add Domain
```

**3. Follow DNS Instructions:**
```
Step 1: Add TXT Record
  Name: _miaobu-verification.www.mysite.com
  Value: miaobu-verification=abc123xyz...
  TTL: 300

Step 2: Add CNAME Record
  Name: www.mysite.com
  Value: cdn.miaobu.app
  TTL: 3600
```

**4. Verify Domain:**
```
Wait 5-10 minutes for DNS propagation
Click "Check DNS" to see current status
Click "Verify Domain" when TXT record is ready
```

**5. Domain Verified:**
```
✅ Domain verified successfully!
Your site is now accessible at www.mysite.com
```

### Apex Domain Setup

**For apex domains (example.com without www):**

```
Step 1: TXT Record
  _miaobu-verification.example.com → miaobu-verification=token

Step 2: A Record (not CNAME)
  example.com → <CDN-IP-Address>
  (Contact support for CDN IP address)
```

Note: Apex domains require special handling because they cannot use CNAME records.

## Testing Guide

### Test 1: Add Domain

1. Go to Project Settings
2. Click "Add Domain"
3. Enter "test.yourdomain.com"
4. Verify domain is created with pending status

### Test 2: DNS Verification

1. Add TXT record to your DNS:
   ```
   _miaobu-verification.test.yourdomain.com
   Value: (copy from Miaobu)
   ```

2. Wait 5-10 minutes for DNS propagation

3. Click "Check DNS" in Miaobu
   - Should show "Has TXT Record: ✅ Yes"

4. Click "Verify Domain"
   - Should show "✅ Domain verified successfully!"

### Test 3: CNAME Configuration

1. After verification, add CNAME record:
   ```
   test.yourdomain.com → cdn.miaobu.app
   ```

2. Wait 5-10 minutes

3. Click "Check DNS"
   - Should show "Has CNAME: ✅ Yes"

4. Visit https://test.yourdomain.com
   - Should see your deployed site!

### Test 4: Delete Domain

1. Click "Delete" on a domain
2. Confirm deletion
3. Verify domain is removed
4. DNS records can be removed manually

## Troubleshooting

### Domain verification fails

**Symptoms:**
- "Verification failed" message
- TXT record not found

**Solutions:**
1. Wait longer (DNS can take up to 48 hours)
2. Check TXT record name is correct
3. Ensure no typos in verification token
4. Try `dig _miaobu-verification.yourdomain.com TXT` to verify

### DNS propagation slow

**Symptoms:**
- DNS not updating
- Old records still showing

**Solutions:**
1. Lower TTL before making changes
2. Wait 24-48 hours for full propagation
3. Use DNS checker tools online
4. Clear local DNS cache

### CNAME conflicts

**Symptoms:**
- Can't add CNAME record
- "Record already exists" error

**Solutions:**
1. Remove existing CNAME or A record
2. For apex domain, use A record instead
3. Check for conflicting records

### CDN not working

**Symptoms:**
- Domain verified but site not loading
- 404 or connection errors

**Solutions:**
1. Verify CNAME points to correct CDN domain
2. Wait for CDN propagation (5-10 minutes)
3. Check CDN domain is configured in .env
4. Verify CDN has domain added

## Security Considerations

### Domain Verification

**Why TXT Record Verification:**
- Proves domain ownership
- Prevents unauthorized domain addition
- Industry standard (used by Let's Encrypt, Google, etc.)
- Secure and reliable

**Token Security:**
- 256 bits of entropy (cryptographically secure)
- Unique per domain
- Cannot be guessed or brute-forced
- URL-safe encoding

### DNS Security

**Best Practices:**
- Use DNSSEC when available
- Enable domain lock
- Monitor DNS changes
- Use 2FA on DNS provider

**Miaobu Protections:**
- Validates domain format
- Checks for duplicates
- Prevents domain hijacking
- Automatic timeout handling

## Performance

### DNS Query Performance

**Verification Check:**
```
Query DNS TXT record: ~50-200ms
Query DNS CNAME record: ~50-200ms
Total verification time: ~100-400ms
```

**Caching:**
- DNS results cached by resolvers
- Reduced verification time on subsequent checks
- TTL respected

### CDN Addition

**Time to Live:**
```
Domain verification: Instant
CDN domain addition: ~30 seconds
CDN propagation: ~5-10 minutes
Full DNS propagation: ~24-48 hours
```

## Cost Analysis

### No Additional Costs!

**Custom domains are free:**
- No per-domain fees
- No verification costs
- No CDN configuration fees
- Only pay for CDN traffic (same as default domain)

**Cost savings:**
- Reuse existing domain (no new domain purchase needed)
- Same CDN pricing as default domain
- No premium for custom domains

## Success Criteria ✅

- ✅ DNS verification service working
- ✅ TXT record verification functional
- ✅ CNAME record checking working
- ✅ Custom domain CRUD API complete
- ✅ Domain verification flow functional
- ✅ CDN domain binding working
- ✅ Frontend domain management UI complete
- ✅ DNS instructions clear and helpful
- ✅ Real-time DNS status checking
- ✅ Multiple domains per project supported

## Limitations & Future Enhancements

### Current Limitations:

1. **Apex domain CNAME:** Cannot use CNAME for apex domains (DNS limitation)
   - Workaround: Use A record with CDN IP

2. **Manual DNS configuration:** User must manually add DNS records
   - Future: API integration with DNS providers

3. **No automatic SSL:** SSL certificates covered in Phase 8
   - Manual SSL possible via CDN console

4. **Single verification method:** Only TXT record verification
   - Future: HTTP file verification, email verification

### Phase 8 Preview:

**Automatic SSL Certificates:**
- Let's Encrypt integration
- Automatic certificate issuance
- Automatic renewal (90 days)
- HTTPS by default
- Certificate management

## Next Phase Preview

**Phase 8: SSL Automation** will add:
- Let's Encrypt integration for free SSL certificates
- Automatic HTTPS enablement for custom domains
- Certificate auto-renewal
- SSL status tracking
- HTTPS-only enforcement

**Current:**
```
www.mysite.com → Domain verified ✓
                → HTTP only (manual SSL)
```

**Phase 8:**
```
www.mysite.com → Domain verified ✓
                → SSL certificate issued ✓
                → HTTPS enabled ✓
                → Auto-renews every 90 days ✓
```

---

**Phase 7 Status: COMPLETE** 🎉

**Custom Domains are LIVE!** 🌐

Users now benefit from:
- ✅ Custom domain support (www.mysite.com)
- ✅ DNS verification for security
- ✅ Step-by-step DNS configuration guide
- ✅ Real-time DNS status checking
- ✅ Automatic CDN integration
- ✅ Multiple domains per project
- ✅ User-friendly domain management UI

Ready to proceed with Phase 8: SSL Automation!
