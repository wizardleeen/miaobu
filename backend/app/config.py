from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_name: str = "Miaobu"
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # Database
    database_url: str

    # Redis (legacy — no longer required, kept for .env compatibility)
    redis_url: str = ""

    # Security
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    github_redirect_uri: str

    # Alibaba Cloud
    aliyun_access_key_id: str
    aliyun_access_key_secret: str
    aliyun_region: str = "cn-hangzhou"
    aliyun_oss_bucket: str
    aliyun_oss_endpoint: str

    # CDN Configuration (Wildcard domain - ONE TIME SETUP)
    # Set up *.metavm.tech → CDN once, then all projects automatically work
    cdn_enabled: bool = True
    cdn_base_domain: str = "metavm.tech"  # Base domain for wildcard (*.metavm.tech)

    # ESA Configuration (Edge Security Acceleration)
    aliyun_esa_enabled: bool = True
    aliyun_esa_site_id: str = ""  # ESA site ID for metavm.tech
    aliyun_esa_site_name: str = "metavm.tech"
    aliyun_esa_cname_target: str = "cname.metavm.tech"
    aliyun_esa_edge_kv_namespace_id: str = "961854465965670400"
    aliyun_esa_edge_kv_namespace: str = "miaobu"
    aliyun_esa_cname_record_id: str = ""  # ESA CNAME DNS record ID for CreateCustomHostname

    # Function Compute Configuration (cn-qingdao for co-location with server)
    aliyun_account_id: str = ""
    aliyun_fc_region: str = "cn-qingdao"
    aliyun_fc_oss_bucket: str = "miaobu-deployments-qingdao"
    aliyun_fc_oss_endpoint: str = "oss-cn-qingdao.aliyuncs.com"
    miaobu_fc_prefix: str = "miaobu"  # FC function name prefix ("kyvy" for staging)
    aliyun_fc_service_name: str = "miaobu"
    aliyun_acr_registry: str = ""  # e.g., "registry.cn-hangzhou.aliyuncs.com"
    aliyun_acr_namespace: str = "miaobu"

    # Function Compute VPC Configuration (for proxy access)
    aliyun_fc_vpc_id: str = ""
    aliyun_fc_vswitch_id: str = ""
    aliyun_fc_security_group_id: str = ""

    # Environment variable encryption
    env_encryption_key: str = ""  # Fernet key for encrypting env var values

    # Build callback (GitHub Actions → Miaobu API)
    miaobu_callback_secret: str = ""  # HMAC-SHA256 secret shared with GHA

    # GitHub PAT for dispatching repository_dispatch events
    github_pat: str = ""

    # HTTP Proxy
    http_proxy: str = ""

    # FC Custom Domain — wildcard certificate for *.{cdn_base_domain}
    fc_wildcard_cert_name: str = ""       # e.g. "metavm-wildcard"
    fc_wildcard_cert_pem: str = ""        # Full-chain PEM certificate
    fc_wildcard_cert_key: str = ""        # PEM private key

    # Anthropic API
    anthropic_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
