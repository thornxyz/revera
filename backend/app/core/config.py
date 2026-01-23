from pathlib import Path
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Gemini Models (hardcoded, not from env)
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_MODEL = "gemini-3-flash-preview"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Revera"
    debug: bool = False

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Google Gemini
    gemini_api_key: str

    # Web Search (Tavily)
    # Web Search (Tavily)
    tavily_api_key: str | None = None

    # Qdrant Settings
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_upsert_batch_size: int = 50

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
