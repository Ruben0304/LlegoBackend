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
    embedding_task_type: str = "RETRIEVAL_DOCUMENT"
    query_task_type: str = "RETRIEVAL_QUERY"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
