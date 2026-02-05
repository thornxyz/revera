"""Supabase client initialization and database operations."""

from functools import lru_cache
from supabase import create_client, Client

from app.core.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """Get cached Supabase client instance."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_anon_client() -> Client:
    """Get Supabase client with anon key (for RLS-enforced operations)."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_service_client() -> Client:
    """
    Get Supabase client with service_role_key for admin operations.

    SECURITY: Only use for background tasks that need to bypass RLS.
    Never expose this client to user-facing endpoints.
    This is used for background critic updates after the user receives their answer.
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase service role configuration missing")

    return create_client(settings.supabase_url, settings.supabase_service_role_key)
