# Production Deployment Guide

Complete guide for deploying Miaobu to production.

## Prerequisites

### Required Services

1. **Server/VM:**
   - Ubuntu 22.04 LTS or later
   - 4 CPU cores minimum
   - 8GB RAM minimum
   - 100GB storage minimum
   - Public IP address

2. **Domain Name:**
   - Domain for API (api.miaobu.app)
   - Domain for frontend (miaobu.app)
   - DNS management access

3. **Alibaba Cloud Account:**
   - OSS bucket configured
   - CDN domain configured
   - DNS access (if using Aliyun DNS)
   - RAM user with appropriate permissions

4. **GitHub OAuth App:**
   - Client ID and Secret
   - Callback URL configured

### Software Requirements

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Nginx
sudo apt update
sudo apt install nginx

# Install Certbot (for SSL)
sudo apt install certbot python3-certbot-nginx
```

## Deployment Steps

### 1. Clone Repository

```bash
# Create deployment directory
sudo mkdir -p /opt/miaobu
sudo chown $USER:$USER /opt/miaobu
cd /opt/miaobu

# Clone repository
git clone <repository-url> .

# Or pull latest changes
git pull origin main
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit environment file
nano .env
```

**Required configuration:**

```bash
# Application
ENVIRONMENT=production
FRONTEND_URL=https://miaobu.app
BACKEND_URL=https://api.miaobu.app

# Database
DATABASE_URL=postgresql://miaobu:STRONG_PASSWORD@postgres:5432/miaobu

# Redis
REDIS_URL=redis://redis:6379/0

# Security
JWT_SECRET_KEY=<generate-strong-random-key>

# GitHub OAuth
GITHUB_CLIENT_ID=<your-client-id>
GITHUB_CLIENT_SECRET=<your-client-secret>
GITHUB_REDIRECT_URI=https://api.miaobu.app/api/v1/auth/github/callback

# Alibaba Cloud
ALIYUN_ACCESS_KEY_ID=<your-key>
ALIYUN_ACCESS_KEY_SECRET=<your-secret>
ALIYUN_REGION=cn-hangzhou
ALIYUN_OSS_BUCKET=<your-bucket>
ALIYUN_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
ALIYUN_CDN_DOMAIN=<your-cdn-domain>
```

**Generate secrets:**

```bash
# Generate JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate database password
openssl rand -base64 32
```

### 3. Build Docker Images

```bash
# Build all services
docker-compose build

# Or build specific service
docker-compose build backend
docker-compose build frontend
docker-compose build worker
```

### 4. Start Services

```bash
# Start all services in background
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend
```

### 5. Run Database Migrations

```bash
# Run migrations
docker-compose exec backend alembic upgrade head

# Verify database
docker-compose exec postgres psql -U miaobu -d miaobu -c "\dt"
```

### 6. Configure Nginx

Create `/etc/nginx/sites-available/miaobu`:

```nginx
# API Backend
server {
    listen 80;
    server_name api.miaobu.app;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.miaobu.app;

    # SSL certificates (will be configured by Certbot)
    ssl_certificate /etc/letsencrypt/live/api.miaobu.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.miaobu.app/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Proxy to backend
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Increase max body size for deployments
    client_max_body_size 100M;
}

# Frontend
server {
    listen 80;
    server_name miaobu.app www.miaobu.app;

    # Redirect to HTTPS
    return 301 https://miaobu.app$request_uri;
}

server {
    listen 443 ssl http2;
    server_name miaobu.app www.miaobu.app;

    # Redirect www to non-www
    if ($host = www.miaobu.app) {
        return 301 https://miaobu.app$request_uri;
    }

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/miaobu.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/miaobu.app/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to frontend
    location / {
        proxy_pass http://localhost:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/miaobu /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Configure SSL Certificates

```bash
# Obtain SSL certificates
sudo certbot --nginx -d api.miaobu.app -d miaobu.app -d www.miaobu.app

# Test auto-renewal
sudo certbot renew --dry-run

# Certificates will auto-renew via systemd timer
sudo systemctl status certbot.timer
```

### 8. Configure Firewall

```bash
# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable
```

### 9. Start Celery Beat (for SSL renewal)

```bash
# Add to docker-compose.yml or run separately
docker-compose exec worker celery -A celery_app beat --loglevel=info &
```

### 10. Verify Deployment

```bash
# Check all services are running
docker-compose ps

# Test API health
curl https://api.miaobu.app/health

# Test frontend
curl https://miaobu.app

# Check logs for errors
docker-compose logs --tail=100

# Test OAuth flow
# Visit https://miaobu.app and try to login
```

## Post-Deployment

### Monitoring Setup

**1. Sentry (Error Tracking):**

```bash
# Add to .env
SENTRY_DSN=<your-sentry-dsn>

# Restart services
docker-compose restart backend frontend
```

**2. System Monitoring:**

```bash
# Install monitoring tools
sudo apt install htop iotop nethogs

# Monitor Docker resources
docker stats

# Monitor disk space
df -h
```

### Backup Configuration

**1. Database Backup:**

```bash
# Create backup script
cat > /opt/miaobu/backup-db.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/opt/miaobu/backups
mkdir -p $BACKUP_DIR

docker-compose exec -T postgres pg_dump -U miaobu miaobu | gzip > $BACKUP_DIR/miaobu_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "miaobu_*.sql.gz" -mtime +7 -delete
EOF

chmod +x /opt/miaobu/backup-db.sh

# Add to crontab
crontab -e
# Add line:
0 2 * * * /opt/miaobu/backup-db.sh
```

**2. Configuration Backup:**

```bash
# Backup environment file
cp .env .env.backup.$(date +%Y%m%d)
```

### Log Rotation

```bash
# Configure Docker log rotation
cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

sudo systemctl restart docker
```

### Security Hardening

**1. SSH Security:**

```bash
# Disable root login
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no

sudo systemctl restart sshd
```

**2. Automatic Updates:**

```bash
# Install unattended-upgrades
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

**3. Fail2ban:**

```bash
# Install fail2ban
sudo apt install fail2ban

# Configure
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## Updating

### Update Application

```bash
cd /opt/miaobu

# Pull latest code
git pull origin main

# Rebuild images
docker-compose build

# Run migrations
docker-compose exec backend alembic upgrade head

# Restart services (zero-downtime)
docker-compose up -d --no-deps --build backend
docker-compose up -d --no-deps --build frontend
docker-compose up -d --no-deps --build worker
```

### Rollback

```bash
# Rollback code
git reset --hard <previous-commit>

# Rollback database
docker-compose exec backend alembic downgrade -1

# Rebuild and restart
docker-compose up -d --build
```

## Troubleshooting

### Services Not Starting

```bash
# Check logs
docker-compose logs backend
docker-compose logs worker

# Check Docker status
docker ps -a

# Restart services
docker-compose restart
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres psql -U miaobu -d miaobu -c "SELECT 1"

# Check DATABASE_URL in .env
```

### Build Failures

```bash
# Check worker logs
docker-compose logs -f worker

# Check disk space
df -h

# Check Docker socket
ls -la /var/run/docker.sock
```

### High Memory Usage

```bash
# Check memory usage
docker stats

# Restart services
docker-compose restart

# Limit container resources in docker-compose.yml
```

### SSL Certificate Issues

```bash
# Check certificate status
sudo certbot certificates

# Renew manually
sudo certbot renew

# Check Nginx configuration
sudo nginx -t
```

## Performance Tuning

### Database Optimization

```sql
-- Add indexes
CREATE INDEX idx_deployments_project_id ON deployments(project_id);
CREATE INDEX idx_deployments_status ON deployments(status);
CREATE INDEX idx_custom_domains_project_id ON custom_domains(project_id);

-- Analyze tables
ANALYZE deployments;
ANALYZE projects;
```

### Redis Optimization

```bash
# Edit redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

### Nginx Caching

```nginx
# Add to nginx config
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m;

location /api/v1/projects {
    proxy_cache api_cache;
    proxy_cache_valid 200 5m;
    # ... rest of config
}
```

## Maintenance

### Regular Tasks

**Daily:**
- Check error logs
- Monitor disk space
- Verify backups

**Weekly:**
- Review monitoring dashboards
- Check SSL certificate expiry
- Update dependencies

**Monthly:**
- Database maintenance (VACUUM, ANALYZE)
- Security updates
- Review access logs

---

## Support

For deployment assistance:
- GitHub Issues: https://github.com/your-repo/issues
- Documentation: https://docs.miaobu.app
- Community: https://community.miaobu.app

---

**Last Updated:** Phase 9 implementation
