# Alibaba Cloud OSS Setup Guide

This guide will help you set up an Alibaba Cloud OSS bucket for Miaobu deployments.

## Prerequisites

- Alibaba Cloud account
- AccessKey ID and AccessKey Secret (RAM user recommended)

## Step 1: Create OSS Bucket

### Via Alibaba Cloud Console

1. **Login to Alibaba Cloud Console**
   - Go to https://oss.console.aliyun.com/

2. **Create Bucket**
   - Click "Create Bucket"
   - Fill in details:
     - **Bucket Name**: `miaobu-deployments` (or your preferred name)
     - **Region**: Choose closest to your users (e.g., `cn-hangzhou`)
     - **Storage Class**: Standard
     - **Access Control List (ACL)**: **Public Read** ⚠️ Important!
     - **Versioning**: Disabled
     - **Server-Side Encryption**: Optional

3. **Click "OK" to create**

### Via Aliyun CLI (Optional)

```bash
# Install Aliyun CLI
brew install aliyun-cli  # macOS
# or download from https://github.com/aliyun/aliyun-cli

# Configure credentials
aliyun configure

# Create bucket with public read access
aliyun oss mb oss://miaobu-deployments --acl public-read
```

## Step 2: Configure Bucket for Static Website Hosting

### Enable Static Website Hosting

1. **Navigate to your bucket** in OSS Console

2. **Click "Basic Settings" → "Static Pages"**

3. **Enable Static Website Hosting:**
   - Default Homepage: `index.html`
   - Default 404 Page: `404.html` (optional)
   - Subdirectory Homepage: Enabled

4. **Click "Save"**

### Set Bucket ACL to Public Read

1. **Go to "Access Control" tab**

2. **Set Bucket ACL:**
   - Select: **Public Read**
   - This allows anyone to read objects in the bucket

3. **Click "Save"**

⚠️ **Security Note:** This makes ALL objects in the bucket publicly readable. Miaobu uses path-based isolation (`user_id/project_id/commit_sha/`) so users can only write to their own paths, but anyone can read any deployment.

## Step 3: Configure CORS (For API Access)

If your frontend makes API calls to deployed sites:

1. **Go to "Access Control" → "Cross-Origin Resource Sharing (CORS)"**

2. **Add CORS Rule:**
   ```
   Allowed Origins: *
   Allowed Methods: GET, HEAD
   Allowed Headers: *
   Expose Headers: ETag, x-oss-request-id
   Max Age: 3600
   ```

3. **Click "Save"**

## Step 4: Create RAM User for Miaobu

For security, create a dedicated RAM user instead of using root credentials:

### Create RAM User

1. **Go to RAM Console**: https://ram.console.aliyun.com/

2. **Create User:**
   - Click "Users" → "Create User"
   - Login Name: `miaobu-deployer`
   - Display Name: `Miaobu Deployer`
   - Access Mode: **Programmatic Access** (API access)

3. **Save AccessKey ID and AccessKey Secret**
   - ⚠️ Save these securely, they won't be shown again!

### Attach OSS Permissions

1. **Click on the created user**

2. **Add Permissions:**
   - Click "Add Permissions"
   - Select: `AliyunOSSFullAccess` (or create custom policy for specific bucket)

3. **Alternative: Custom Policy (More Secure)**

   Create a custom policy with minimal permissions:

   ```json
   {
     "Version": "1",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "oss:PutObject",
           "oss:GetObject",
           "oss:DeleteObject",
           "oss:ListObjects"
         ],
         "Resource": [
           "acs:oss:*:*:miaobu-deployments",
           "acs:oss:*:*:miaobu-deployments/*"
         ]
       }
     ]
   }
   ```

## Step 5: Configure Miaobu

Update your `.env` file with OSS credentials:

```bash
# Alibaba Cloud OSS Configuration
ALIYUN_ACCESS_KEY_ID=LTAI5t...  # Your AccessKey ID
ALIYUN_ACCESS_KEY_SECRET=xxxxx  # Your AccessKey Secret
ALIYUN_REGION=cn-hangzhou       # Your OSS region
ALIYUN_OSS_BUCKET=miaobu-deployments  # Your bucket name
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com  # OSS endpoint for your region

# Optional: CDN domain (Phase 5)
# ALIYUN_CDN_DOMAIN=cdn.miaobu.app
```

### OSS Endpoint by Region

Common regions and endpoints:

| Region | Endpoint |
|--------|----------|
| Hangzhou (华东1) | `oss-cn-hangzhou.aliyuncs.com` |
| Shanghai (华东2) | `oss-cn-shanghai.aliyuncs.com` |
| Beijing (华北2) | `oss-cn-beijing.aliyuncs.com` |
| Shenzhen (华南1) | `oss-cn-shenzhen.aliyuncs.com` |
| Hong Kong | `oss-cn-hongkong.aliyuncs.com` |

Full list: https://www.alibabacloud.com/help/en/oss/user-guide/regions-and-endpoints

## Step 6: Test OSS Configuration

### Via Python Script

Create a test script to verify OSS access:

```python
import oss2

# Your credentials
auth = oss2.Auth('YOUR_ACCESS_KEY_ID', 'YOUR_ACCESS_KEY_SECRET')
bucket = oss2.Bucket(auth, 'oss-cn-hangzhou.aliyuncs.com', 'miaobu-deployments')

# Test upload
bucket.put_object('test.txt', 'Hello Miaobu!')
print("✓ Upload successful")

# Test public read
url = f"https://miaobu-deployments.oss-cn-hangzhou.aliyuncs.com/test.txt"
print(f"✓ Public URL: {url}")

# Test delete
bucket.delete_object('test.txt')
print("✓ Delete successful")

print("\n✓ OSS configuration is working!")
```

### Via Miaobu API

After starting Miaobu:

```bash
# Check if OSS service initializes without errors
docker-compose logs worker | grep OSS

# Trigger a deployment and check logs
# Should see "STEP 5: UPLOADING TO OSS" in deployment logs
```

## Troubleshooting

### Error: "The bucket you are attempting to access must be addressed using the specified endpoint"

**Solution:** Check that `ALIYUN_OSS_ENDPOINT` matches your bucket's region.

### Error: "AccessDenied"

**Solutions:**
1. Verify AccessKey ID and Secret are correct
2. Check RAM user has OSS permissions
3. Verify bucket ACL is set to Public Read

### Error: "NoSuchBucket"

**Solutions:**
1. Check bucket name in `.env` matches actual bucket name
2. Verify bucket exists in the OSS console

### Error: "SignatureDoesNotMatch"

**Solutions:**
1. Verify AccessKey Secret is correct (no extra spaces)
2. Check system time is synchronized (OSS validates timestamps)

### Deployments succeed but files not accessible

**Solutions:**
1. Check bucket ACL is set to **Public Read**
2. Verify static website hosting is enabled
3. Check object ACL (should inherit bucket ACL)
4. Test URL directly in browser

## Cost Estimation

Alibaba Cloud OSS pricing (as of 2024):

### Storage
- Standard Storage: ~¥0.12/GB/month (~$0.017/GB/month)
- Example: 100 projects × 10 deployments × 5MB = 5GB = ~¥0.60/month

### Data Transfer
- Outbound to Internet: ¥0.50/GB (~$0.07/GB)
- Internal transfer (same region): Free
- CDN acceleration: Separate pricing (Phase 5)

### Requests
- PUT requests: ¥0.01/10,000 requests
- GET requests: ¥0.01/10,000 requests

**Typical Monthly Cost for Small-Medium Usage:**
- Storage (10GB): ~¥1.20
- Transfer (100GB): ~¥50
- Requests (1M): ~¥1
- **Total: ~¥52/month (~$7/month)**

## Security Best Practices

1. **Use RAM Users**
   - Don't use root account credentials
   - Create dedicated RAM user for Miaobu

2. **Minimal Permissions**
   - Only grant necessary OSS permissions
   - Limit to specific bucket if possible

3. **Rotate Credentials**
   - Regularly rotate AccessKey
   - Update `.env` when rotating

4. **Monitor Access**
   - Enable OSS logging
   - Monitor for unusual activity

5. **Consider Bucket Policy**
   - Further restrict access if needed
   - Use IP whitelist for PUT operations (advanced)

## Advanced Configuration

### Enable OSS Logging

Track access to your deployments:

```bash
# Enable logging via CLI
aliyun oss logging --method put \
  --bucket miaobu-deployments \
  --target-bucket miaobu-logs \
  --target-prefix oss-logs/
```

### Set Object Lifecycle Rules

Auto-delete old deployments:

1. Go to "Basic Settings" → "Lifecycle"
2. Create rule:
   - Prefix: `*/*/*/` (all deployments)
   - Expiration: 90 days
3. Saves storage costs by cleaning old deployments

### Enable Server-Side Encryption

For sensitive deployments:

1. Go to "Basic Settings" → "Server-Side Encryption"
2. Choose encryption method:
   - AES256 (free)
   - KMS (additional cost)

## Next Steps

After completing OSS setup:

1. **Restart Miaobu services:**
   ```bash
   docker-compose restart worker backend
   ```

2. **Test deployment:**
   - Import a repository
   - Trigger deployment
   - Check logs for OSS upload
   - Verify files are accessible

3. **Phase 5 (Optional):** Set up CDN for faster global access

---

**Questions?** Check the troubleshooting section or open an issue on GitHub.
