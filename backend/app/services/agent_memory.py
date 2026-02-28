"""Agent Memory Service using LangGraph Store for long-term memory."""

import asyncio
import logging
from uuid import UUID
from typing import Any

from langgraph.store.base import BaseStore

from app.core.memory_store import get_memory_store

logger = logging.getLogger(__name__)


class AgentMemoryService:
    """
    Manages agent long-term memory using LangGraph Store.

    Memory is organized by namespace: (user_id, chat_id, memory_type, agent_name)
    - memory_type can be: "episodic" (past executions), "semantic" (facts), "procedural" (instructions)

    Supports sliding window memory management to keep recent context relevant.
    """

    MEMORY_WINDOW_SIZE = 10  # Keep last 10 messages in full detail

    def __init__(self, store: BaseStore | None = None):
        """Initialize memory service with optional custom store."""
        self.store = store or get_memory_store()

    async def store_agent_memory(
        self,
        user_id: UUID,
        chat_id: UUID,
        message_id: UUID,
        agent_name: str,
        memory_state: dict[str, Any],
    ) -> None:
        """
        Store agent execution state as episodic memory.

        Args:
            user_id: User ID for namespacing
            chat_id: Chat ID for namespacing
            message_id: Unique message ID (used as key)
            agent_name: Name of agent (planner, retrieval, synthesis, critic)
            memory_state: Agent's execution state/output
        """
        namespace = (str(user_id), str(chat_id), "episodic", agent_name)

        logger.info(
            f"[MEMORY] Storing {agent_name} memory for message_id={message_id}, namespace={namespace}"
        )

        try:
            await asyncio.to_thread(
                self.store.put,
                namespace,
                str(message_id),
                {
                    **memory_state,
                    "message_id": str(message_id),
                    "agent_name": agent_name,
                },
            )
            logger.info(
                f"[MEMORY] Successfully stored {agent_name} memory for message {message_id}"
            )
        except Exception as e:
            logger.error(
                f"[MEMORY] Failed to store {agent_name} memory: {e}", exc_info=True
            )

    async def get_agent_memory(
        self,
        user_id: UUID,
        chat_id: UUID,
        agent_name: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent memories for a specific agent in a chat.

        Args:
            user_id: User ID
            chat_id: Chat ID
            agent_name: Agent to retrieve memories for
            limit: Max number of memories (default: MEMORY_WINDOW_SIZE)

        Returns:
            List of memory states (most recent first)
        """
        namespace = (str(user_id), str(chat_id), "episodic", agent_name)
        limit = limit or self.MEMORY_WINDOW_SIZE

        logger.info(
            f"[MEMORY] Retrieving {agent_name} memories for chat_id={chat_id}, limit={limit}"
        )

        try:
            items = await asyncio.to_thread(
                self.store.search,
                namespace,
                limit=limit,
            )

            memories = [item.value for item in items]
            logger.info(f"[MEMORY] Retrieved {len(memories)} memories for {agent_name}")
            return memories

        except Exception as e:
            logger.error(
                f"[MEMORY] Failed to retrieve {agent_name} memories: {e}", exc_info=True
            )
            return []

    async def build_memory_context(
        self,
        user_id: UUID,
        chat_id: UUID,
        current_query: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Build memory context for all agents in parallel.

        Args:
            user_id: User ID
            chat_id: Chat ID
            current_query: Optional query for semantic search

        Returns:
            Dict mapping agent names to their memory lists
        """
        agents = ["planner", "retrieval", "synthesis", "critic"]

        logger.info(
            f"[MEMORY] Building memory context for chat_id={chat_id}, query={current_query[:50] if current_query else 'None'}..."
        )

        def _search_sync(agent: str) -> list[dict[str, Any]]:
            namespace = (str(user_id), str(chat_id), "episodic", agent)
            search_kwargs: dict[str, Any] = {"limit": self.MEMORY_WINDOW_SIZE}
            if current_query:
                search_kwargs["query"] = current_query
            items = self.store.search(namespace, **search_kwargs)
            return [item.value for item in items]

        async def fetch_agent_memories(agent: str) -> tuple[str, list[dict[str, Any]]]:
            try:
                memories = await asyncio.to_thread(_search_sync, agent)
                return agent, memories
            except Exception as e:
                logger.error(
                    f"[MEMORY] Failed to build context for {agent}: {e}", exc_info=True
                )
                return agent, []

        results = await asyncio.gather(
            *[fetch_agent_memories(agent) for agent in agents]
        )
        memory_context = dict(results)

        total_memories = sum(len(v) for v in memory_context.values())
        logger.info(
            f"[MEMORY] Built context with {total_memories} total memories across {len(agents)} agents"
        )
        return memory_context

    async def store_semantic_memory(
        self,
        user_id: UUID,
        chat_id: UUID,
        key: str,
        facts: dict[str, Any],
    ) -> None:
        """
        Store semantic facts/learnings about this chat.

        Examples: relevant document IDs, user preferences, patterns

        Args:
            user_id: User ID
            chat_id: Chat ID
            key: Unique key for this fact set (e.g., "relevant_documents")
            facts: Dictionary of facts to store
        """
        namespace = (str(user_id), str(chat_id), "semantic")

        try:
            await asyncio.to_thread(
                self.store.put,
                namespace,
                key,
                facts,
            )
            logger.debug(f"[MEMORY] Stored semantic memory: {key}")
        except Exception as e:
            logger.error(f"[MEMORY] Failed to store semantic memory {key}: {e}")

    async def get_semantic_memory(
        self,
        user_id: UUID,
        chat_id: UUID,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Retrieve semantic memories (facts) for this chat.

        Args:
            user_id: User ID
            chat_id: Chat ID
            query: Optional query for semantic search
            limit: Max facts to retrieve

        Returns:
            List of fact dictionaries
        """
        namespace = (str(user_id), str(chat_id), "semantic")

        try:
            # Build search with optional query parameter
            search_kwargs: dict[str, Any] = {"limit": limit}
            if query:
                search_kwargs["query"] = query

            items = await asyncio.to_thread(
                self.store.search, namespace, **search_kwargs
            )

            facts = [item.value for item in items]
            logger.debug(f"[MEMORY] Retrieved {len(facts)} semantic memories")
            return facts

        except Exception as e:
            logger.error(f"[MEMORY] Failed to retrieve semantic memories: {e}")
            return []

    def format_memory_for_prompt(
        self,
        agent_name: str,
        memories: list[dict[str, Any]],
    ) -> str:
        """
        Format agent memories into a prompt-ready string.

        Args:
            agent_name: Name of the agent
            memories: List of memory states

        Returns:
            Formatted string for injection into agent prompts
        """
        if not memories:
            return ""

        # Agent-specific formatting
        if agent_name == "planner":
            return self._format_planner_memory(memories)
        elif agent_name == "retrieval":
            return self._format_retrieval_memory(memories)
        elif agent_name == "synthesis":
            return self._format_synthesis_memory(memories)
        elif agent_name == "critic":
            return self._format_critic_memory(memories)
        else:
            return ""

    def _format_planner_memory(self, memories: list[dict[str, Any]]) -> str:
        """Format planner memory for prompt injection."""
        recent_plans = [m.get("plan", "") for m in memories[:3] if m.get("plan")]

        if not recent_plans:
            return ""

        return f"""
Previous planning strategies in this conversation:
{chr(10).join(f"- {plan}" for plan in recent_plans)}

Consider these past approaches when planning the current query.
""".strip()

    def _format_retrieval_memory(self, memories: list[dict[str, Any]]) -> str:
        """Format retrieval memory for prompt injection."""
        # Extract document IDs that were highly relevant
        seen: set[str] = set()
        relevant_docs: list[str] = []

        for mem in memories[:5]:
            sources = mem.get("sources", [])
            for source in sources:
                if isinstance(source, dict) and source.get("score", 0) > 0.7:
                    doc_id = source.get("document_id")
                    if doc_id and doc_id not in seen:
                        seen.add(doc_id)
                        relevant_docs.append(doc_id)

        if not relevant_docs:
            return ""

        return f"""
Previously relevant documents in this conversation: {relevant_docs}
Prioritize these if they match the current query context.
""".strip()

    def _format_synthesis_memory(self, memories: list[dict[str, Any]]) -> str:
        """Format synthesis memory for prompt injection."""
        recent_answers = []

        for mem in memories[:3]:
            answer = mem.get("answer", "")
            if answer:
                # Truncate long answers
                snippet = answer[:200] + "..." if len(answer) > 200 else answer
                recent_answers.append(snippet)

        if not recent_answers:
            return ""

        return f"""
Recent answers in this conversation:
{chr(10).join(f"- {ans}" for ans in recent_answers)}

Maintain consistency with previous responses while addressing the new query.
""".strip()

    def _format_critic_memory(self, memories: list[dict[str, Any]]) -> str:
        """Format critic memory for prompt injection."""
        if not memories:
            return ""

        # Track verification patterns
        verified_count = sum(
            1 for m in memories[:5] if m.get("confidence") == "verified"
        )
        total = min(len(memories), 5)
        avg_confidence = verified_count / total if total > 0 else 0

        return f"""
Verification history for this chat:
- Average confidence: {avg_confidence:.0%}
- Past verifications: {len(memories)} messages checked

Apply similar verification rigor to this response.
""".strip()


_agent_memory_service: AgentMemoryService | None = None


def get_agent_memory_service() -> AgentMemoryService:
    """Get the process-wide singleton AgentMemoryService."""
    global _agent_memory_service
    if _agent_memory_service is None:
        _agent_memory_service = AgentMemoryService()
    return _agent_memory_service
