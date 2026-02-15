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

    # Redis
    redis_url: str

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

    # HTTP Proxy
    http_proxy: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
