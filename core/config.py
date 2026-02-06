"""Application configuration using pydantic-settings."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB Configuration
    mongodb_url: str
    mongodb_database: str = "llego"

    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: str = ""  # Optional para Qdrant Cloud
    qdrant_https: bool = False  # True para producción/Railway
    qdrant_prefer_grpc: bool = False  # False para conexiones públicas, True para red privada Railway
    qdrant_timeout: int = 60  # Timeout en segundos - Aumentado para Railway cold starts

    # Gemini API Configuration
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimension: int = 768

    # AI Assistant quota configuration
    ai_free_lifetime_limit: int = 2
    ai_pro_monthly_limit: int = 60
    ai_usage_collection: str = "ai_quota_usage"

    # Embedding Configuration
    # Embedding Configuration
    embedding_task_type: str = "RETRIEVAL_DOCUMENT"
    query_task_type: str = "RETRIEVAL_QUERY"
    
    # Auth Configuration
    google_client_id: str = "your-google-client-id"
    apple_client_id: str = "your-apple-client-id"
    jwt_secret: str = ""
    
    # Push Notifications - Bundle ID for APNs (can be different from auth bundle)
    apns_bundle_id: str = ""  # If empty, uses first apple_client_id
    apns_key_id: str = ""  # Key ID for push notifications (if different from auth)
    apns_private_key: str = ""  # Private key for push (.p8 content)
    apns_use_sandbox: bool = True  # True for development/TestFlight, False for App Store
    
    # Apple Web Auth (for Android/Kotlin)
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""  # Contenido del .p8 (sin archivo)
    apple_web_service_id: str = ""
    apple_web_redirect_uri: str = ""

    # CORS Configuration
    # Comma-separated list of allowed origins for web
    cors_origins_str: str = "http://localhost:3000"
    
    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins_str.split(",") if origin.strip()]

    # Environment
    environment: str = "development"  # "development" or "production"

    # Redis Configuration (for rate limiting)
    redis_url: str = "redis://localhost:6379"

    # Cache Configuration
    # CACHE_ALL_ON_STARTUP: If true, preload all data at startup (no TTL, permanent until restart)
    # If false, use on-demand caching with TTL
    cache_all_on_startup: bool = False
    # CACHE_TTL: TTL in seconds for on-demand cache mode (only used when cache_all_on_startup=false)
    cache_ttl: int = 1800  # 30 minutes default
    # CACHE_PRESIGNED_URL_TTL: TTL for S3 presigned URLs (always uses TTL since URLs expire)
    cache_presigned_url_ttl: int = 3000  # 50 minutes (URLs expire in 60)

    # Stripe Configuration
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # AWS Configuration
    aws_access_key_id: str
    aws_default_region: str
    aws_endpoint_url: str
    aws_secret_access_key: str
    s3_bucket_name: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
