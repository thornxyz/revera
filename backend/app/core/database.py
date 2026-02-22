"""Supabase client initialization and database operations."""

import logging
from functools import lru_cache
from supabase import create_client, Client

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_supabase_client() -> Client:
    """Get cached Supabase client instance."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_anon_client() -> Client:
    """Get Supabase client with anon key (for RLS-enforced operations)."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_service_client(*, caller: str = "unknown") -> Client:
    """
    Get Supabase client with service_role_key for admin operations.

    SECURITY: Only use for background tasks that need to bypass RLS.
    Never expose this client to user-facing endpoints.

    Args:
        caller: Human-readable name of the calling function/module for audit.
                Always pass __name__ or a descriptive label.
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise ValueError("Supabase service role configuration missing")

    logger.warning(
        "[AUDIT] Service-role client created (RLS bypassed)",
        extra={"audit_caller": caller},
    )

    return create_client(settings.supabase_url, settings.supabase_service_role_key)
