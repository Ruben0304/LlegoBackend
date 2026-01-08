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
    qdrant_timeout: int = 10  # Timeout en segundos

    # Gemini API Configuration
    gemini_api_key: str
    gemini_model: str = "gemini-embedding-001"
    embedding_dimension: int = 768

    # Embedding Configuration
    # Embedding Configuration
    embedding_task_type: str = "RETRIEVAL_DOCUMENT"
    query_task_type: str = "RETRIEVAL_QUERY"
    
    # Auth Configuration
    google_client_id: str = "your-google-client-id"
    apple_client_id: str = "your-apple-client-id"
    jwt_secret: str = ""

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
