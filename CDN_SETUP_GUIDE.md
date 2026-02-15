# Alibaba Cloud CDN Setup Guide

This guide will help you set up Alibaba Cloud CDN for faster global access to your Miaobu deployments.

## Why Use CDN?

**Benefits:**
- ⚡ **Faster global access** - Content served from edge locations near users
- 💰 **Lower bandwidth costs** - CDN traffic typically cheaper than OSS direct
- 🛡️ **DDoS protection** - Built-in protection against attacks
- 📊 **Better performance** - Automatic caching and optimization
- 🌍 **Global reach** - 2800+ nodes worldwide

**Performance Comparison:**
```
Without CDN (OSS Direct):
  US → China OSS: ~500-1000ms
  Europe → China OSS: ~300-600ms

With CDN:
  US → CDN Edge: ~50-100ms
  Europe → CDN Edge: ~30-80ms
```

## Prerequisites

- Alibaba Cloud account with CDN service enabled
- OSS bucket already configured (see OSS_SETUP_GUIDE.md)
- Domain name (optional, can use Aliyun-provided domain)

## Option 1: Quick Setup (Aliyun Subdomain)

Use Aliyun's provided `.alikunlun.com` domain for quick testing.

### Step 1: Enable CDN for OSS Bucket

1. **Login to Alibaba Cloud Console**
   - Go to https://cdn.console.aliyun.com/

2. **Add CDN Domain**
   - Click "Add Domain"
   - Domain Name: `your-bucket-name.alikunlun.com` (auto-generated)
   - Business Type: **Download/Distribution**
   - Origin: **OSS Domain**
   - Select your OSS bucket

3. **CDN Configuration**
   - Click "Next"
   - Default settings are fine for testing

4. **Get CNAME**
   - After creation, note the CNAME: `xxxx.w.alikunlun.com`

### Step 2: Configure Miaobu

Update `.env`:
```bash
ALIYUN_CDN_DOMAIN=your-bucket-name.alikunlun.com
```

Restart services:
```bash
docker-compose restart worker backend
```

That's it! Your next deployment will use CDN.

## Option 2: Custom Domain Setup

Use your own domain (e.g., `cdn.miaobu.app`) for production.

### Step 1: Add Domain to CDN

1. **Go to CDN Console**
   - https://cdn.console.aliyun.com/

2. **Add CDN Domain**
   - Domain: `cdn.yourdomain.com`
   - Business Type: **Download/Distribution**
   - Origin: **OSS Domain**
   - Origin Address: Select your OSS bucket

3. **Advanced Settings:**
   - **Port**: 443 (HTTPS) and 80 (HTTP)
   - **Region**: Global or specific regions
   - **Cache Rules**: Default (or customize)

4. **Click "Submit"**

### Step 2: Configure DNS (CNAME)

After CDN domain is added, you'll get a CNAME record:
```
cdn.yourdomain.com → xxx.w.kunlunsl.com
```

**Configure DNS:**

```
# Example with Cloudflare
Type: CNAME
Name: cdn
Content: xxx.w.kunlunsl.com
Proxy: OFF (important!)
TTL: Auto
```

**Or with Aliyun DNS:**
```bash
# Via Aliyun DNS console
Record Type: CNAME
Host: cdn
Value: xxx.w.kunlunsl.com
TTL: 10 minutes
```

**Verify DNS propagation:**
```bash
# Should return CDN CNAME
dig cdn.yourdomain.com

# Or
nslookup cdn.yourdomain.com
```

### Step 3: Enable HTTPS (SSL Certificate)

#### Option A: Free Aliyun Certificate

1. **Go to CDN Console → Your Domain → HTTPS Settings**

2. **Enable HTTPS:**
   - HTTPS Certificate: **Free Certificate**
   - Auto-renew: Enabled
   - Force HTTPS: Enabled (redirects HTTP to HTTPS)

3. **Click "Confirm"**

Certificate will be issued automatically (takes 5-10 minutes).

#### Option B: Custom Certificate

If you have your own certificate:

1. **Upload Certificate:**
   - Certificate Content: Paste your cert
   - Private Key: Paste your key
   - Certificate Name: Descriptive name

2. **Enable HTTPS:**
   - Select your certificate
   - Force HTTPS: Enabled

### Step 4: Configure Cache Rules

Optimize caching for static sites:

1. **Go to CDN Console → Your Domain → Cache Configuration**

2. **Add Cache Rule:**

```
Rule 1: HTML Files (Short Cache)
  Path: *.html
  Cache Expiration: 10 minutes
  Priority: 10

Rule 2: Static Assets (Long Cache)
  Path: *.js,*.css,*.png,*.jpg,*.woff,*.woff2
  Cache Expiration: 7 days
  Priority: 5

Rule 3: Default (Medium Cache)
  Path: *
  Cache Expiration: 1 hour
  Priority: 1
```

3. **Click "Save"**

### Step 5: Configure Miaobu

Update `.env`:
```bash
ALIYUN_CDN_DOMAIN=cdn.yourdomain.com
```

Restart services:
```bash
docker-compose restart worker backend
```

## Cache Purge Configuration

Miaobu automatically purges CDN cache after each deployment.

### Manual Cache Purge

If needed, you can manually purge cache:

**Via Console:**
1. Go to CDN Console → Refresh & Prefetch
2. Enter URLs or directories to purge
3. Click "Submit"

**Via CLI:**
```bash
aliyun cdn RefreshObjectCaches \
  --ObjectPath="https://cdn.yourdomain.com/1/5/abc123.../" \
  --ObjectType=Directory
```

### Cache Purge API

Miaobu uses the CDN API to purge cache automatically:

```python
# Purges entire deployment directory
POST /api/v1/cdn/purge
{
  "deployment_id": 123
}
```

## Advanced Configuration

### Custom Cache Keys

Ignore query strings for better cache hit rates:

1. **Go to Cache Configuration → Cache Key**
2. **Ignore Parameters:**
   - Enable: Yes
   - Retain Parameters: (none)
   - This makes `?v=1` and `?v=2` return same cached file

### Gzip Compression

Already enabled by default, but you can configure:

1. **Go to Performance Optimization → Intelligent Compression**
2. **Gzip Compression:**
   - Enable: Yes
   - File Types: text/*, application/javascript, etc.

### Origin Protection

Prevent direct OSS access, force through CDN:

1. **Go to Back-to-Origin → Origin Host**
2. **Configure:**
   - Back-to-Origin Host: Your OSS bucket domain
   - Use OSS private bucket + CDN auth (advanced)

### Access Control

Restrict access by region or IP:

1. **Go to Access Control → IP Blacklist/Whitelist**
2. **Configure as needed**

**Or URL Authentication:**
1. **Go to Access Control → URL Authentication**
2. **Enable Auth Type A/B/C**
3. **Set authentication key**

## Performance Optimization

### Prefetch/Warming

Warm up cache after deployment:

```bash
# Miaobu can do this automatically
# Just enable in settings
ALIYUN_CDN_PREFETCH_ENABLED=true
```

### HTTP/2

Enable HTTP/2 for better performance:

1. **Go to HTTPS Settings**
2. **HTTP/2:** Enable

### QUIC

Enable QUIC (HTTP/3) for even better performance:

1. **Go to HTTPS Settings**
2. **QUIC:** Enable (if available in your region)

## Monitoring and Analytics

### View CDN Usage

1. **Go to CDN Console → Usage**
2. **View metrics:**
   - Bandwidth usage
   - Request count
   - Status codes
   - Traffic by region

### Set Up Alerts

1. **Go to Cloud Monitor**
2. **Create alarm:**
   - Metric: CDN bandwidth/requests
   - Threshold: Your limit
   - Notification: Email/SMS

## Cost Optimization

### CDN Pricing

Alibaba Cloud CDN charges based on:
- **Traffic** (primary cost)
- **HTTPS requests** (if HTTPS enabled)
- **Purge operations** (usually free or very cheap)

**Pricing Tiers (Traffic):**
```
0-10TB:     ¥0.24/GB (~$0.033/GB)
10-50TB:    ¥0.23/GB
50-100TB:   ¥0.21/GB
100TB+:     ¥0.15/GB
```

**Cost Comparison:**
```
OSS Direct (100GB/month):
  100GB × ¥0.50/GB = ¥50/month

CDN (100GB/month):
  100GB × ¥0.24/GB = ¥24/month
  Savings: 52%!
```

### Cost Optimization Tips

1. **Long cache times** - Reduces origin fetches
2. **Gzip compression** - Reduces traffic by 70%
3. **Smart purging** - Only purge what changed
4. **Regional CDN** - Use CN-only for Chinese users
5. **Cache warmup** - Reduces origin traffic

## Troubleshooting

### CNAME not resolving

**Symptoms:**
- Domain doesn't resolve
- DNS errors

**Solutions:**
1. Check DNS propagation (can take up to 48 hours)
2. Verify CNAME record is correct
3. Ensure proxy is OFF (if using Cloudflare)
4. Test with `dig` or `nslookup`

### CDN serving stale content

**Symptoms:**
- New deployment not showing
- Old content still visible

**Solutions:**
1. Check cache purge was triggered
2. Manually purge cache
3. Check cache rules (TTL might be too long)
4. Force refresh: Ctrl+F5 in browser

### SSL certificate errors

**Symptoms:**
- HTTPS not working
- Certificate errors

**Solutions:**
1. Wait for certificate issuance (5-10 minutes)
2. Check certificate is active in CDN console
3. Verify domain matches certificate
4. Try different browser

### Slow CDN performance

**Symptoms:**
- CDN slower than expected
- High latency

**Solutions:**
1. Check origin performance (OSS might be slow)
2. Verify cache hit rate (should be >80%)
3. Enable HTTP/2 and QUIC
4. Check if using correct region

### Cache purge not working

**Symptoms:**
- Manual or auto purge fails
- Logs show purge errors

**Solutions:**
1. Verify CDN domain in `.env` is correct
2. Check RAM user has CDN permissions
3. Verify CDN API is enabled
4. Check Aliyun API limits

## Security Best Practices

### Use HTTPS Only

Force HTTPS redirect:
```
HTTP → HTTPS (automatic redirect)
```

### Enable Referer Protection

Prevent hotlinking:
```
Allowed Referers: *.yourdomain.com
Empty Referer: Allow (for direct access)
```

### IP Restrictions

For sensitive deployments:
```
Whitelist: Your company IP ranges
Blacklist: Known bad actors
```

### Rate Limiting

Prevent abuse:
```
Rate limit: 1000 requests/minute per IP
```

## Testing CDN Setup

### Test 1: Basic Access

```bash
# Should return your site
curl -I https://cdn.yourdomain.com/1/5/abc123.../index.html

# Check headers
# Should see: X-Cache: HIT (after first request)
```

### Test 2: Cache Hit

```bash
# First request (cache MISS)
curl -I https://cdn.yourdomain.com/...

# Second request (cache HIT)
curl -I https://cdn.yourdomain.com/...

# Look for:
# X-Cache: HIT
# X-Cache-Lookup: Hit From MemCache
```

### Test 3: Cache Purge

```bash
# Deploy new version
# Check logs for "CDN cache purge initiated"

# Verify purge
curl https://cdn.yourdomain.com/...
# Should show new content
```

### Test 4: Performance

```bash
# Test from different locations
curl -w "@curl-format.txt" -o /dev/null -s https://cdn.yourdomain.com/...

# Compare with OSS direct
curl -w "@curl-format.txt" -o /dev/null -s https://bucket.oss.aliyuncs.com/...
```

**curl-format.txt:**
```
time_namelookup: %{time_namelookup}\n
time_connect: %{time_connect}\n
time_starttransfer: %{time_starttransfer}\n
time_total: %{time_total}\n
```

## Next Steps

After CDN is configured:

1. **Deploy a test project**
   - Watch logs for CDN URL
   - Verify cache purge messages

2. **Test performance**
   - Compare CDN vs OSS direct
   - Check cache hit rates

3. **Monitor costs**
   - Watch CDN usage in console
   - Set up billing alerts

4. **Fine-tune cache rules**
   - Adjust TTLs based on usage
   - Optimize for your needs

---

**Questions?** Check troubleshooting section or Alibaba Cloud CDN documentation.
