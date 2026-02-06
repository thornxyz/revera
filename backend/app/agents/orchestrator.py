"""Orchestrator - Coordinates agent execution for research queries using LangGraph."""

import logging
import time
from uuid import uuid4, UUID
from dataclasses import dataclass

from app.agents.graph_builder import compile_research_graph
from app.agents.graph_state import ResearchState
from app.core.database import get_supabase_client
from app.core.utils import sanitize_for_postgres
from app.services.agent_memory import get_agent_memory_service

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Complete result of a research query."""

    session_id: str
    query: str
    answer: str
    sources: list[dict]
    verification: dict
    agent_timeline: list[dict]
    total_latency_ms: int
    confidence: str


class Orchestrator:
    """
    LangGraph-based orchestrator for multi-agent research workflow.

    Features:
    - Parallel execution of retrieval + web search
    - Conditional routing based on execution plan
    - Feedback loops for answer refinement
    - Streaming support for real-time updates
    - State-based architecture for better observability
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        logger.info(f"[ORCH] Initializing LangGraph orchestrator for user: {user_id}")
        self.supabase = get_supabase_client()

        # Compile the research graph once at initialization
        self.graph = compile_research_graph()
        logger.info("[ORCH] LangGraph workflow compiled and ready")

    def _log_agent_timeline(self, session_id: str, timeline: list[dict]):
        """Log all agent executions to database."""
        for entry in timeline:
            try:
                self.supabase.table("agent_logs").insert(
                    {
                        "session_id": session_id,
                        "agent_name": entry.get("agent_name"),
                        "events": {
                            "result_summary": str(entry.get("result", ""))[:500],
                            "metadata": entry.get("metadata", {}),
                        },
                        "latency_ms": entry.get("latency_ms", 0),
                    }
                ).execute()
            except Exception as e:
                logger.warning(
                    f"[ORCH] Failed to log agent {entry.get('agent_name')}: {e}"
                )

    @staticmethod
    def _normalize_sources(
        internal_sources: list[dict], web_sources: list[dict]
    ) -> list[dict]:
        """Normalize sources for storage and API responses."""
        normalized_internal = [
            {
                "type": "internal",
                "chunk_id": source.get("chunk_id"),
                "document_id": source.get("document_id"),
                "content": source.get("content", ""),
                "score": source.get("score", 0),
            }
            for source in internal_sources
        ]

        normalized_web = [
            {
                "type": "web",
                "url": source.get("url"),
                "title": source.get("title"),
                "content": source.get("content", ""),
                "score": source.get("relevance_score", source.get("score", 0)),
            }
            for source in web_sources
        ]

        return normalized_internal + normalized_web

    async def research_stream_with_context(
        self,
        query: str,
        chat_id: UUID,
        thread_id: str,
        use_web: bool = True,
        document_ids: list[str] | None = None,
        max_iterations: int = 2,
    ):
        """
        Execute research with chat context and streaming updates.

        Uses LangGraph's astream_events to drive the compiled graph while
        streaming node status, answer/thought chunks, and sources back to
        the caller (which wraps them as SSE in chats.py).
        """
        start_time = time.perf_counter()
        session_id = str(uuid4())

        # --- Pre-graph setup (memory, doc validation, session row) ---

        memory_service = get_agent_memory_service()
        memory_context = await memory_service.build_memory_context(
            user_id=UUID(self.user_id),
            chat_id=chat_id,
            current_query=query,
        )

        # Enforce Chat-Scoped Document Validation
        chat_documents = (
            self.supabase.table("documents")
            .select("id")
            .eq("chat_id", str(chat_id))
            .execute()
        )
        chat_scoped_document_ids: list[str] = []
        if chat_documents.data:
            chat_scoped_document_ids = [
                str(d.get("id", ""))
                for d in chat_documents.data
                if isinstance(d, dict) and d.get("id")
            ]
        logger.info(
            f"[ORCH] Enforcing chat scope: {len(chat_scoped_document_ids)} documents for chat {chat_id}"
        )

        try:
            self.supabase.table("research_sessions").insert(
                {
                    "id": session_id,
                    "user_id": self.user_id,
                    "query": query,
                    "status": "running",
                    "chat_id": str(chat_id),
                    "thread_id": thread_id,
                }
            ).execute()
        except Exception as e:
            logger.error(f"[ORCH] Failed to create session: {e}")
            raise

        # Yield message_id early so the frontend can track this message
        yield {"type": "message_id", "message_id": session_id}

        # --- Build initial state for LangGraph ---

        initial_state: ResearchState = {
            "query": query,
            "user_id": self.user_id,
            "session_id": session_id,
            "use_web": use_web,
            "document_ids": chat_scoped_document_ids,
            "chat_id": str(chat_id),
            "thread_id": thread_id,
            "execution_plan": None,
            "internal_sources": [],
            "web_sources": [],
            "image_contexts": [],
            "synthesis_result": None,
            "verification": None,
            "agent_timeline": [],
            "iteration_count": 0,
            "needs_refinement": False,
            "max_iterations": max_iterations,
            "memory_context": memory_context,
        }

        # Track outputs collected from graph events
        agent_timeline: list[dict] = []
        internal_sources: list[dict] = []
        web_sources: list[dict] = []
        synthesis_result: dict | None = None
        verification: dict | None = None

        known_nodes = {"planning", "retrieval", "web_search", "synthesis", "critic"}

        try:
            # --- Stream the LangGraph graph ---

            config: dict = {"configurable": {"thread_id": thread_id}}

            async for event in self.graph.astream_events(
                initial_state,
                version="v2",
                config=config,  # type: ignore[arg-type]
            ):
                kind = event.get("event")
                name = event.get("name", "")

                # Node lifecycle: started
                if kind == "on_chain_start" and name in known_nodes:
                    yield {
                        "type": "node_complete",
                        "node": name,
                        "status": "running",
                    }

                # Node lifecycle: completed
                elif kind == "on_chain_end" and name in known_nodes:
                    yield {
                        "type": "node_complete",
                        "node": name,
                        "status": "complete",
                    }

                    # Capture output from each node for post-graph usage
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        if "internal_sources" in output:
                            internal_sources = output["internal_sources"]
                        if "web_sources" in output:
                            web_sources = output["web_sources"]
                        if "synthesis_result" in output:
                            synthesis_result = output["synthesis_result"]
                        if "verification" in output:
                            verification = output["verification"]
                        if "agent_timeline" in output:
                            agent_timeline.extend(output["agent_timeline"])

                # Custom events dispatched by nodes (answer/thought/sources)
                elif kind == "on_custom_event":
                    if name == "answer_chunk":
                        yield {
                            "type": "answer_chunk",
                            "content": event["data"].get("content", ""),
                        }
                    elif name == "thought_chunk":
                        yield {
                            "type": "thought_chunk",
                            "content": event["data"].get("content", ""),
                        }
                    elif name == "sources":
                        yield {
                            "type": "sources",
                            "sources": event["data"].get("sources", []),
                        }

            # --- Post-graph: normalize, persist, yield final events ---

            all_sources = self._normalize_sources(internal_sources, web_sources)
            yield {"type": "sources", "sources": all_sources}

            total_latency = int((time.perf_counter() - start_time) * 1000)

            # Determine confidence from real verification result
            confidence = "unknown"
            if verification:
                confidence = verification.get("verification_status", "unknown")

            # Store agent memories
            logger.info("[ORCH] Storing agent memories...")
            try:
                await self._store_agent_memories(
                    chat_id=chat_id,
                    session_id=session_id,
                    agent_timeline=agent_timeline,
                )
                logger.info("[ORCH] Agent memories stored successfully")
            except Exception as mem_err:
                logger.error(
                    f"[ORCH] Failed to store memories: {mem_err}",
                    exc_info=True,
                )

            # Update research session
            logger.info("[ORCH] Updating session in database...")
            try:
                self.supabase.table("research_sessions").update(
                    sanitize_for_postgres(
                        {
                            "status": "completed",
                            "result": {
                                "answer": (
                                    synthesis_result.get("answer", "")
                                    if synthesis_result
                                    else ""
                                ),
                                "sources": all_sources,
                                "verification": verification,
                                "confidence": confidence,
                                "total_latency_ms": total_latency,
                                "query": query,
                                "session_id": session_id,
                            },
                        }
                    )
                ).eq("id", session_id).execute()
                logger.info("[ORCH] Session updated successfully")
            except Exception as db_err:
                logger.error(
                    f"[ORCH] Failed to update session: {db_err}",
                    exc_info=True,
                )

            self._log_agent_timeline(session_id, agent_timeline)

            # Update chat title based on query
            from app.services.title_generator import generate_title_from_query

            new_title = generate_title_from_query(query)
            logger.info(f"[ORCH] Updating chat {chat_id} title to: {new_title}")

            try:
                self.supabase.table("chats").update({"title": new_title}).eq(
                    "id", str(chat_id)
                ).execute()
                logger.info("[ORCH] Chat title updated successfully")

                yield {
                    "type": "title_updated",
                    "title": new_title,
                    "chat_id": str(chat_id),
                }
            except Exception as title_err:
                logger.error(f"[ORCH] Failed to update chat title: {title_err}")

            # Yield final complete event with definitive answer
            answer = ""
            if synthesis_result:
                answer = synthesis_result.get("answer", "")

            logger.info("[ORCH] Yielding final complete event")
            yield {
                "type": "complete",
                "session_id": session_id,
                "confidence": confidence,
                "total_latency_ms": total_latency,
                "sources": all_sources,
                "verification": verification,
                "agent_timeline": agent_timeline,
                "answer": answer,
            }
            logger.info("[ORCH] Stream complete!")

        except Exception as e:
            logger.error(f"[ORCH] Research failed: {e}", exc_info=True)
            try:
                self.supabase.table("research_sessions").update(
                    {"status": "failed", "result": {"error": str(e)}}
                ).eq("id", session_id).execute()
            except Exception as db_err:
                logger.error(f"[ORCH] DB update failed: {db_err}")
            yield {"type": "error", "message": str(e)}

    async def _store_agent_memories(
        self,
        chat_id: UUID,
        session_id: str,
        agent_timeline: list[dict],
    ):
        """Store agent execution states as memories in Store."""
        memory_service = get_agent_memory_service()
        message_id = UUID(session_id)  # Use session_id as message_id

        for entry in agent_timeline:
            agent_name = entry.get("agent_name", "")

            # Extract relevant state from each agent
            memory_state = {
                "result_summary": str(entry.get("result", ""))[:500],
                "metadata": entry.get("metadata", {}),
                "latency_ms": entry.get("latency_ms", 0),
            }

            # Agent-specific memory extraction
            if agent_name == "planner":
                result = entry.get("result")
                # ExecutionPlan is a dataclass with subtasks, steps, constraints
                if result and hasattr(result, "subtasks") and result.subtasks:
                    # Store subtasks as the plan summary
                    memory_state["plan"] = ", ".join(result.subtasks)
                elif isinstance(result, dict):
                    memory_state["plan"] = result.get("approach", "")
            elif agent_name == "retrieval":
                memory_state["sources"] = entry.get("result", [])[:5]  # Top 5
            elif agent_name == "synthesis":
                result = entry.get("result", {})
                if isinstance(result, dict):
                    memory_state["answer"] = result.get("answer", "")[:500]
            elif agent_name == "critic":
                result = entry.get("result", {})
                if isinstance(result, dict):
                    memory_state["confidence"] = result.get("verification_status", "")

            try:
                await memory_service.store_agent_memory(
                    user_id=UUID(self.user_id),
                    chat_id=chat_id,
                    message_id=message_id,
                    agent_name=agent_name,
                    memory_state=memory_state,
                )
            except Exception as e:
                logger.warning(f"[ORCH] Failed to store memory for {agent_name}: {e}")
