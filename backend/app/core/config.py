from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Gemini Models (hardcoded, not from env)
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# Gemini Thinking Configuration
GEMINI_THINKING_LEVEL = "medium"  # Options: minimal, low, medium, high


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Revera"
    debug: bool = False

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Google Gemini
    gemini_api_key: str = ""

    # Web Search (Tavily)
    tavily_api_key: str | None = None

    # Qdrant Settings
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_upsert_batch_size: int = 50

    # Server Configuration
    cors_origins: list[str] = ["http://localhost:3000"]
    critic_timeout_seconds: int = 30
    log_format: str = "text"  # "text" or "json"

    # File Upload Limits
    max_file_size_mb: int = 50  # For PDFs
    max_image_size_mb: int = 10  # For images

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
