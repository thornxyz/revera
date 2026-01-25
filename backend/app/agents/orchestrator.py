"""Orchestrator - Coordinates agent execution for research queries using LangGraph."""

import logging
import time
from uuid import uuid4
from dataclasses import dataclass

from app.agents.graph_builder import compile_research_graph
from app.agents.graph_state import ResearchState
from app.core.database import get_supabase_client

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

    New features compared to old implementation:
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

    async def research(
        self,
        query: str,
        use_web: bool = True,
        document_ids: list[str] | None = None,
        max_iterations: int = 2,
    ) -> ResearchResult:
        """
        Execute a complete research query using the LangGraph workflow.

        Args:
            query: The research question
            use_web: Whether to use web search
            document_ids: Optional list of specific document IDs to search
            max_iterations: Maximum refinement iterations (default: 2)

        Returns:
            ResearchResult with answer, sources, verification, and timeline
        """
        start_time = time.perf_counter()

        # Create research session
        session_id = str(uuid4())
        logger.info(f"[ORCH] Creating session: {session_id}")

        try:
            self.supabase.table("research_sessions").insert(
                {
                    "id": session_id,
                    "user_id": self.user_id,
                    "query": query,
                    "status": "running",
                }
            ).execute()
            logger.info("[ORCH] Session created in DB")
        except Exception as e:
            logger.error(f"[ORCH] Failed to create session: {e}")
            raise

        try:
            # Initialize the graph state
            initial_state: ResearchState = {
                "query": query,
                "user_id": self.user_id,
                "session_id": session_id,
                "use_web": use_web,
                "document_ids": document_ids,
                "execution_plan": None,
                "internal_sources": [],
                "web_sources": [],
                "synthesis_result": None,
                "verification": None,
                "agent_timeline": [],
                "iteration_count": 0,
                "needs_refinement": False,
                "max_iterations": max_iterations,
            }

            logger.info("[ORCH] Invoking LangGraph workflow...")

            # Execute the graph
            final_state = await self.graph.ainvoke(initial_state)

            logger.info("[ORCH] LangGraph workflow completed")

            # Extract results from final state
            synthesis_result = final_state.get("synthesis_result", {})
            verification = final_state.get("verification", {})
            agent_timeline = final_state.get("agent_timeline", [])
            internal_sources = final_state.get("internal_sources", [])
            web_sources = final_state.get("web_sources", [])

            # Calculate total latency
            total_latency = int((time.perf_counter() - start_time) * 1000)

            # Combine all sources
            all_sources = self._normalize_sources(internal_sources, web_sources)

            # Safely extract answer with fallback
            answer = synthesis_result.get("answer", "")
            if not answer or not isinstance(answer, str):
                logger.warning(
                    f"[ORCH] Invalid answer in synthesis_result: {type(answer)}. "
                    "Using fallback message."
                )
                answer = (
                    "I apologize, but I encountered an issue generating a response. "
                    "Please try rephrasing your question or contact support if this persists."
                )

            # Build final result
            result = ResearchResult(
                session_id=session_id,
                query=query,
                answer=answer,
                sources=all_sources,
                verification=verification,
                agent_timeline=agent_timeline,
                total_latency_ms=total_latency,
                confidence=verification.get("verification_status", "unknown"),
            )

            # Log agent execution to database
            self._log_agent_timeline(session_id, agent_timeline)

            # Update session status
            logger.info("[ORCH] Updating session status to completed...")
            self.supabase.table("research_sessions").update(
                {
                    "status": "completed",
                    "result": {
                        "answer": result.answer,
                        "sources": all_sources,
                        "verification": verification,
                        "confidence": result.confidence,
                        "total_latency_ms": result.total_latency_ms,
                        "query": query,
                        "session_id": session_id,
                        "iterations": final_state.get("iteration_count", 0),
                    },
                }
            ).eq("id", session_id).execute()

            logger.info(
                f"[ORCH] Research complete! Total: {total_latency}ms, Iterations: {final_state.get('iteration_count', 0)}"
            )
            return result

        except Exception as e:
            logger.error(f"[ORCH] Research failed: {e}", exc_info=True)
            # Update session with error
            try:
                self.supabase.table("research_sessions").update(
                    {
                        "status": "failed",
                        "result": {"error": str(e)},
                    }
                ).eq("id", session_id).execute()
            except Exception as db_err:
                logger.error(f"[ORCH] Failed to update session status: {db_err}")
            raise

    async def research_stream(
        self,
        query: str,
        use_web: bool = True,
        document_ids: list[str] | None = None,
        max_iterations: int = 2,
    ):
        """
        Execute research with streaming updates.

        Yields state updates as each node completes.
        This allows the frontend to show real-time progress.
        """
        session_id = str(uuid4())

        try:
            self.supabase.table("research_sessions").insert(
                {
                    "id": session_id,
                    "user_id": self.user_id,
                    "query": query,
                    "status": "running",
                }
            ).execute()
        except Exception as e:
            logger.error(f"[ORCH] Failed to create session: {e}")
            raise

        initial_state: ResearchState = {
            "query": query,
            "user_id": self.user_id,
            "session_id": session_id,
            "use_web": use_web,
            "document_ids": document_ids,
            "execution_plan": None,
            "internal_sources": [],
            "web_sources": [],
            "synthesis_result": None,
            "verification": None,
            "agent_timeline": [],
            "iteration_count": 0,
            "needs_refinement": False,
            "max_iterations": max_iterations,
        }

        # Stream graph execution
        async for event in self.graph.astream(initial_state):
            # Each event is a dict with node name as key
            for node_name, node_output in event.items():
                logger.info(f"[ORCH] Stream update from node: {node_name}")
                yield {
                    "type": "node_complete",
                    "node": node_name,
                    "data": node_output,
                }

        # Final update
        yield {
            "type": "complete",
            "session_id": session_id,
        }

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
