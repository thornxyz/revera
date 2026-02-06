"""LangGraph Store configuration for long-term agent memory."""

import logging
from functools import lru_cache
from typing import Callable

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


def get_embedding_function() -> Callable[[list[str]], list[list[float]]]:
    """
    Create embedding function for semantic search in Store.

    Uses Gemini embedding model for vector similarity search.
    """
    client = get_gemini_client()

    def embed(texts: list[str]) -> list[list[float]]:
        """Embed texts using Gemini embedding model."""
        if not texts:
            return []

        # Use Gemini embedding model (batch)
        embeddings = []
        for text in texts:
            result = client.embed_text(text=text)
            embeddings.append(result)

        return embeddings

    return embed


@lru_cache
def get_memory_store() -> BaseStore:
    """
    Get cached LangGraph Store instance.

    Store is used for long-term agent memory (semantic, episodic, procedural).
    Uses in-memory storage with vector search capabilities.

    NOTE: Agent memory is ephemeral and lost on restart. This is intentional
    to keep the system simple. Chat conversations and messages persist in
    Supabase regardless of this setting.

    Returns:
        InMemoryStore: In-memory store with vector search support
    """
    logger.info(
        "[MEMORY_STORE] Initializing InMemoryStore for agent long-term memory. "
        "Agent learnings are ephemeral (lost on restart). "
        "Chat history persists in Supabase database."
    )

    return InMemoryStore(
        index={
            "embed": get_embedding_function(),
            "dims": 3072,  # Gemini embedding-001 outputs 3072-dimensional vectors
        }
    )
