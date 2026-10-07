"""Configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # LLM Configuration
    llm_provider: str = "ollama"  # "ollama" or "anthropic"
    llm_model: str = "qwen2.5:14b-instruct"  # Default; falls back to 7b-instruct if memory constrained
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: str | None = None

    # Embeddings Configuration
    embeddings_model: str = "all-MiniLM-L6-v2"

    # Storage Configuration
    db_path: str = "tracepaper.db"
    database_url: str = "postgresql+psycopg://tracepaper:tracepaper@localhost:5432/tracepaper"
    cache_dir: str = ".cache"
    invite_expiry_hours: int = 72
    session_expiry_hours: int = 12

    # Logging Configuration
    log_level: str = "info"

    # Feature Flags
    cache_enabled: bool = True  # Disk cache for LLM calls

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
