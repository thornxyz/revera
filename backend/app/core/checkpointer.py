"""LangGraph checkpointer backed by Supabase Postgres.

Uses `langgraph-checkpoint-postgres` with a connection pool for
persistent graph state per thread_id. Enables multi-turn conversations
to preserve full LangGraph state across server restarts.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton — typed as Any to avoid importing psycopg_pool at
# module level (the binary wheel may not be installed at import time).
_pool = None
_checkpointer_instance = None


async def get_checkpointer():
    """
    Get or create a singleton AsyncPostgresSaver backed by a connection pool.

    The checkpointer persists LangGraph graph state (checkpoints) in
    Supabase Postgres. It automatically creates its tables on first use
    via `.setup()`.

    Requires `SUPABASE_DB_URL` in environment (direct Postgres connection string).
    Requires `psycopg[binary]` and `langgraph-checkpoint-postgres` to be installed.

    Returns:
        AsyncPostgresSaver instance, or None if DB URL is not configured or
        dependencies are unavailable.
    """
    global _pool, _checkpointer_instance

    if _checkpointer_instance is not None:
        return _checkpointer_instance

    settings = get_settings()
    db_url = settings.supabase_db_url

    if not db_url:
        logger.warning(
            "[CHECKPOINTER] SUPABASE_DB_URL not configured. "
            "Graph state will NOT be persisted across restarts. "
            "Set SUPABASE_DB_URL to enable LangGraph checkpointing."
        )
        return None

    try:
        # Both imports are deferred so a missing psycopg binary wheel or
        # missing libpq never causes a crash at module-import time.
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # Create connection pool (min 1, max 5 connections).
        # autocommit=True and prepare_threshold=0 are required for
        # Supabase Supavisor (PgBouncer-style) connection pooling.
        _pool = AsyncConnectionPool(
            conninfo=db_url,
            min_size=1,
            max_size=5,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
            },
        )
        await _pool.open()

        _checkpointer_instance = AsyncPostgresSaver(conn=_pool)

        # Create checkpointer tables if they don't exist (idempotent)
        await _checkpointer_instance.setup()

        logger.info(
            "[CHECKPOINTER] AsyncPostgresSaver initialized with connection pool. "
            "Graph state will persist across restarts."
        )
        return _checkpointer_instance

    except Exception as e:
        logger.error(
            f"[CHECKPOINTER] Failed to initialize: {e}. "
            "Graph state will NOT be persisted.",
            exc_info=True,
        )
        # Close pool if it was opened before the failure (e.g. setup() error)
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
        _pool = None
        _checkpointer_instance = None
        return None


async def close_checkpointer():
    """Close the connection pool on application shutdown."""
    global _pool, _checkpointer_instance

    if _pool is not None:
        try:
            await _pool.close()
            logger.info("[CHECKPOINTER] Connection pool closed")
        except Exception as e:
            logger.error(f"[CHECKPOINTER] Error closing pool: {e}")
        finally:
            _pool = None
            _checkpointer_instance = None
