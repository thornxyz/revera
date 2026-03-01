"""LangGraph Store configuration for long-term agent memory.

Uses Supabase-backed persistent storage instead of ephemeral InMemoryStore.
Agent learnings now persist across server restarts.
"""

import logging
from functools import lru_cache

from langgraph.store.base import BaseStore

from app.core.supabase_memory_store import SupabaseMemoryStore

logger = logging.getLogger(__name__)


@lru_cache
def get_memory_store() -> BaseStore:
    """
    Get cached LangGraph Store instance.

    Store is used for long-term agent memory (semantic, episodic, procedural).
    Backed by the `agent_memory` table in Supabase for persistence.

    Returns:
        SupabaseMemoryStore: Supabase-backed store with persistent storage
    """
    logger.info(
        "[MEMORY_STORE] Initializing SupabaseMemoryStore for persistent "
        "agent long-term memory. Agent learnings persist across restarts "
        "in the agent_memory table."
    )

    return SupabaseMemoryStore()
