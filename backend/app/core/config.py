from pydantic_settings import BaseSettings
from functools import lru_cache


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
    gemini_embedding_model: str = "models/text-embedding-004"
    gemini_reasoning_model: str = "gemini-1.5-pro"
    gemini_fast_model: str = "gemini-1.5-flash"

    # Web Search (optional for now)
    web_search_api_key: str | None = None
    web_search_provider: str = "tavily"  # tavily, serper, bing

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
