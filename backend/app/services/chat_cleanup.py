"""Chat cleanup service for complete deletion of chat and associated data."""

import logging

from postgrest import CountMethod
from qdrant_client import models

from app.core.database import get_supabase_client
from app.core.memory_store import get_memory_store
from app.core.qdrant import get_qdrant_service

logger = logging.getLogger(__name__)


class ChatCleanupService:
    """
    Handles comprehensive deletion of chat and all associated data.

    Deletion Order (children before parents):
    1. Agent memories (InMemoryStore - episodic/semantic)
    2. Document embeddings (Qdrant vectors filtered by chat_id)
    3. Documents (embeddings cascade delete via Qdrant)
    4. Agent logs (cascade from research_sessions)
    5. Research sessions
    6. Messages
    7. Chat record
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.qdrant = get_qdrant_service()
        self.memory_store = get_memory_store()

    async def delete_chat_completely(self, chat_id: str, user_id: str) -> dict:
        """
        Delete a chat and ALL associated data across all systems.

        Args:
            chat_id: Chat UUID to delete
            user_id: User UUID (for verification and cleanup)

        Returns:
            Dict with deletion summary statistics

        Raises:
            ValueError: If chat not found or user doesn't own it
        """
        logger.info(f"[CLEANUP] Starting complete deletion for chat_id={chat_id}")

        # Verify chat exists and user owns it
        chat = (
            self.supabase.table("chats")
            .select("id, user_id")
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not chat.data:
            logger.warning(
                f"[CLEANUP] Chat not found or user doesn't own it: chat_id={chat_id}, user_id={user_id}"
            )
            raise ValueError("Chat not found")

        stats = {
            "chat_id": chat_id,
            "agent_memories_deleted": 0,
            "document_embeddings_deleted": 0,
            "documents_deleted": 0,
            "research_sessions_deleted": 0,
            "messages_deleted": 0,
        }

        # Step 1: Delete agent memories from InMemoryStore
        logger.info("[CLEANUP] Step 1/6: Deleting agent memories...")
        stats["agent_memories_deleted"] = await self._delete_agent_memories(
            user_id, chat_id
        )

        # Step 2: Delete document embeddings from Qdrant (handled in step 3)
        logger.info(
            "[CLEANUP] Step 2/6: Preparing to delete document embeddings (via document_id)..."
        )
        stats["document_embeddings_deleted"] = await self._delete_document_embeddings(
            chat_id
        )

        # Step 3: Delete documents (cascades to document_chunks in DB)
        logger.info("[CLEANUP] Step 3/6: Deleting documents...")
        stats["documents_deleted"] = await self._delete_documents(chat_id, user_id)

        # Step 4: Delete research sessions (cascades to agent_logs in DB)
        logger.info("[CLEANUP] Step 4/6: Deleting research sessions...")
        stats["research_sessions_deleted"] = await self._delete_research_sessions(
            chat_id, user_id
        )

        # Step 5: Delete messages
        logger.info("[CLEANUP] Step 5/6: Deleting messages...")
        stats["messages_deleted"] = await self._delete_messages(chat_id, user_id)

        # Step 6: Delete chat record
        logger.info("[CLEANUP] Step 6/6: Deleting chat record...")
        self.supabase.table("chats").delete().eq("id", chat_id).eq(
            "user_id", user_id
        ).execute()

        logger.info(
            f"[CLEANUP] ✅ Complete deletion finished for chat_id={chat_id}. Stats: {stats}"
        )
        return stats

    async def _delete_agent_memories(self, user_id: str, chat_id: str) -> int:
        """
        Delete all agent memories for this chat from InMemoryStore.

        Memory namespaces:
        - Episodic: (user_id, chat_id, "episodic", agent_name)
        - Semantic: (user_id, chat_id, "semantic")
        """
        deleted_count = 0
        agents = ["planner", "retrieval", "synthesis", "critic"]

        try:
            # Delete episodic memories for each agent
            for agent in agents:
                namespace = (str(user_id), str(chat_id), "episodic", agent)
                try:
                    # Search for all items in this namespace
                    items = self.memory_store.search(namespace, limit=1000)
                    for item in items:
                        self.memory_store.delete(namespace, item.key)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(
                        f"[CLEANUP] Failed to delete episodic memories for {agent}: {e}"
                    )

            # Delete semantic memories
            semantic_namespace = (str(user_id), str(chat_id), "semantic")
            try:
                items = self.memory_store.search(semantic_namespace, limit=1000)
                for item in items:
                    self.memory_store.delete(semantic_namespace, item.key)
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"[CLEANUP] Failed to delete semantic memories: {e}")

            logger.info(f"[CLEANUP] Deleted {deleted_count} agent memories")
        except Exception as e:
            logger.error(f"[CLEANUP] Error deleting agent memories: {e}", exc_info=True)

        return deleted_count

    async def _delete_document_embeddings(self, chat_id: str) -> int:
        """
        Delete all document embeddings for this chat from Qdrant.

        Note: This method is actually redundant because _delete_documents()
        already deletes embeddings by document_id. Keeping it for completeness
        and as a safety net.
        """
        # Document embeddings don't store chat_id directly in Qdrant payload.
        # They're deleted via document_id in _delete_documents().
        # This is just a placeholder that returns 0.
        logger.info(
            "[CLEANUP] Skipping direct Qdrant deletion (handled by _delete_documents)"
        )
        return 0

    async def _delete_documents(self, chat_id: str, user_id: str) -> int:
        """
        Delete all documents for this chat.

        This will cascade to document_chunks via database foreign keys.
        Also deletes embeddings from Qdrant by document_id.
        """
        deleted_count = 0

        try:
            # Get all documents for this chat
            docs_result = (
                self.supabase.table("documents")
                .select("id")
                .eq("chat_id", chat_id)
                .eq("user_id", user_id)
                .execute()
            )

            documents = docs_result.data or []

            for doc in documents:
                doc_id: str = doc["id"]  # type: ignore
                try:
                    # Delete vectors from Qdrant (by document_id)
                    self.qdrant.get_client().delete(
                        collection_name=self.qdrant.collection_name,
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="document_id",
                                        match=models.MatchValue(value=str(doc_id)),
                                    )
                                ]
                            )
                        ),
                    )

                    # Delete document record (cascades to chunks)
                    self.supabase.table("documents").delete().eq("id", doc_id).execute()

                    deleted_count += 1
                except Exception as e:
                    logger.error(
                        f"[CLEANUP] Failed to delete document {doc_id}: {e}",
                        exc_info=True,
                    )

            logger.info(f"[CLEANUP] Deleted {deleted_count} documents")

        except Exception as e:
            logger.error(f"[CLEANUP] Error deleting documents: {e}", exc_info=True)

        return deleted_count

    async def _delete_research_sessions(self, chat_id: str, user_id: str) -> int:
        """
        Delete all research sessions for this chat.

        This will cascade to agent_logs via database foreign keys.
        """
        try:
            # Count sessions before deletion
            count_result = (
                self.supabase.table("research_sessions")
                .select("id", count=CountMethod.exact)
                .eq("chat_id", chat_id)
                .eq("user_id", user_id)
                .execute()
            )

            session_count: int = count_result.count or 0

            # Delete all sessions (cascades to agent_logs)
            self.supabase.table("research_sessions").delete().eq("chat_id", chat_id).eq(
                "user_id", user_id
            ).execute()

            logger.info(f"[CLEANUP] Deleted {session_count} research sessions")
            return session_count

        except Exception as e:
            logger.error(
                f"[CLEANUP] Error deleting research sessions: {e}", exc_info=True
            )
            return 0

    async def _delete_messages(self, chat_id: str, user_id: str) -> int:
        """Delete all messages for this chat."""
        try:
            # Count messages before deletion
            count_result = (
                self.supabase.table("messages")
                .select("id", count=CountMethod.exact)
                .eq("chat_id", chat_id)
                .eq("user_id", user_id)
                .execute()
            )

            message_count: int = count_result.count or 0

            # Delete all messages
            self.supabase.table("messages").delete().eq("chat_id", chat_id).eq(
                "user_id", user_id
            ).execute()

            logger.info(f"[CLEANUP] Deleted {message_count} messages")
            return message_count

        except Exception as e:
            logger.error(f"[CLEANUP] Error deleting messages: {e}", exc_info=True)
            return 0


# Singleton
_cleanup_service: ChatCleanupService | None = None


def get_cleanup_service() -> ChatCleanupService:
    """Get or create cleanup service instance."""
    global _cleanup_service
    if _cleanup_service is None:
        _cleanup_service = ChatCleanupService()
    return _cleanup_service
