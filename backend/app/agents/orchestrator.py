"""Orchestrator - Coordinates agent execution for research queries using LangGraph."""

import asyncio
import logging
import time
from uuid import uuid4, UUID
from dataclasses import dataclass

from app.agents.graph_builder import compile_research_graph
from app.agents.graph_state import ResearchState
from app.core.database import get_supabase_client
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
        Execute research with streaming updates including answer tokens.

        Yields:
        - agent_status events as each node starts/completes
        - answer_chunk events with streaming synthesis text
        - sources event with retrieved sources
        - complete event with final session info
        """
        import time
        from app.agents.base import AgentInput
        from app.agents.planner import PlannerAgent
        from app.agents.retrieval import RetrievalAgent
        from app.agents.web_search import WebSearchAgent
        from app.agents.synthesis import SynthesisAgent
        from app.agents.critic import CriticAgent

        start_time = time.perf_counter()
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

        agent_timeline = []
        internal_sources = []
        web_sources = []
        synthesis_result = None
        verification = None

        try:
            # 1. Planning
            yield {"type": "node_complete", "node": "planning", "status": "running"}
            planner = PlannerAgent()
            plan_input = AgentInput(query=query, constraints={"use_web": use_web})
            plan_output = await planner.run(plan_input)
            execution_plan = plan_output.result
            agent_timeline.append(plan_output.to_dict())
            yield {"type": "node_complete", "node": "planning", "status": "complete"}

            # 2. Retrieval
            yield {"type": "node_complete", "node": "retrieval", "status": "running"}
            retrieval = RetrievalAgent(self.user_id)
            retrieval_input = AgentInput(
                query=query,
                context={"document_ids": document_ids},
                constraints=execution_plan.constraints if execution_plan else {},
            )
            retrieval_output = await retrieval.run(retrieval_input)
            internal_sources = retrieval_output.result
            agent_timeline.append(retrieval_output.to_dict())
            yield {"type": "node_complete", "node": "retrieval", "status": "complete"}

            # Yield sources immediately after retrieval
            yield {"type": "sources", "sources": internal_sources}

            # 3. Web Search (conditional)
            should_web_search = use_web
            if execution_plan and hasattr(execution_plan, "steps"):
                should_web_search = use_web and any(
                    step.tool == "web" for step in execution_plan.steps
                )

            if should_web_search:
                yield {
                    "type": "node_complete",
                    "node": "web_search",
                    "status": "running",
                }
                web_search = WebSearchAgent()
                web_input = AgentInput(
                    query=query,
                    constraints=execution_plan.constraints if execution_plan else {},
                )
                web_output = await web_search.run(web_input)
                web_sources = web_output.result
                agent_timeline.append(web_output.to_dict())
                yield {
                    "type": "node_complete",
                    "node": "web_search",
                    "status": "complete",
                }
                # Yield web sources
                yield {"type": "sources", "sources": web_sources}

            # 4. Synthesis with streaming!
            yield {"type": "node_complete", "node": "synthesis", "status": "running"}
            synthesis = SynthesisAgent()
            synthesis_input = AgentInput(
                query=query,
                context={
                    "internal_sources": internal_sources,
                    "web_sources": web_sources,
                },
                constraints=execution_plan.constraints if execution_plan else {},
            )

            # Stream the synthesis answer
            async for chunk in synthesis.run_stream(synthesis_input):
                if chunk.get("type") == "thought_chunk":
                    yield {"type": "thought_chunk", "content": chunk.get("content", "")}
                elif chunk.get("type") == "answer_chunk":
                    yield {"type": "answer_chunk", "content": chunk.get("content", "")}
                elif chunk.get("type") == "complete":
                    logger.info("[ORCH] Received synthesis complete event")
                    synthesis_output = chunk.get("output")
                    synthesis_result = (
                        synthesis_output.result if synthesis_output else {}
                    )
                    if synthesis_output:
                        agent_timeline.append(synthesis_output.to_dict())

            yield {"type": "node_complete", "node": "synthesis", "status": "complete"}

            # Yield sources immediately after synthesis (don't wait for critic)
            all_sources = self._normalize_sources(internal_sources, web_sources)
            yield {"type": "sources", "sources": all_sources}
            logger.info(f"[ORCH] Sent sources event: {len(all_sources)} total sources")

            # 5. Critic/Verification (with timeout and error handling)
            yield {"type": "node_complete", "node": "critic", "status": "running"}
            verification = None
            try:
                critic = CriticAgent()
                critic_input = AgentInput(
                    query=query,
                    context={
                        "synthesis_result": synthesis_result,
                        "internal_sources": internal_sources,
                        "web_sources": web_sources,
                    },
                )
                # Add timeout to prevent hanging (30 seconds)
                critic_output = await asyncio.wait_for(
                    critic.run(critic_input), timeout=30.0
                )
                verification = critic_output.result
                agent_timeline.append(critic_output.to_dict())
                yield {"type": "node_complete", "node": "critic", "status": "complete"}
            except asyncio.TimeoutError:
                logger.warning(
                    "[ORCH] Critic timed out after 30s, continuing without verification"
                )
                verification = {
                    "verification_status": "timeout",
                    "issues": ["Verification timed out"],
                }
                yield {"type": "node_complete", "node": "critic", "status": "timeout"}
            except Exception as e:
                logger.error(f"[ORCH] Critic failed: {e}", exc_info=True)
                verification = {
                    "verification_status": "error",
                    "issues": [f"Verification error: {str(e)}"],
                }
                yield {"type": "node_complete", "node": "critic", "status": "error"}

            # Calculate total latency
            total_latency = int((time.perf_counter() - start_time) * 1000)

            # Note: all_sources already computed and sent earlier (line 323-325)

            # Update session in database
            self.supabase.table("research_sessions").update(
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
                        "confidence": (
                            verification.get("verification_status", "unknown")
                            if verification
                            else "unknown"
                        ),
                        "total_latency_ms": total_latency,
                        "query": query,
                        "session_id": session_id,
                    },
                }
            ).eq("id", session_id).execute()

            # Log agent timeline
            self._log_agent_timeline(session_id, agent_timeline)

            # Final complete event
            yield {
                "type": "complete",
                "session_id": session_id,
                "confidence": (
                    verification.get("verification_status", "unknown")
                    if verification
                    else "unknown"
                ),
                "total_latency_ms": total_latency,
                "sources": all_sources,
                "verification": verification,
            }

        except Exception as e:
            logger.error(f"[ORCH] Stream research failed: {e}", exc_info=True)
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
            yield {"type": "error", "message": str(e)}

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

    async def research_with_context(
        self,
        query: str,
        chat_id: UUID,
        thread_id: str,
        use_web: bool = True,
        document_ids: list[str] | None = None,
        max_iterations: int = 2,
    ) -> ResearchResult:
        """
        Execute research with chat context and agent memory.

        This method:
        1. Fetches agent memory from Store (long-term)
        2. Injects memory context into initial state
        3. Stores new agent memories after execution

        Args:
            query: The research question
            chat_id: Chat ID for memory scoping
            thread_id: LangGraph thread ID (for logging/tracking)
            use_web: Whether to use web search
            document_ids: Optional document IDs (chat-scoped)
            max_iterations: Max refinement iterations

        Returns:
            ResearchResult with answer, sources, verification, and timeline
        """
        start_time = time.perf_counter()
        session_id = str(uuid4())

        logger.info(
            f"[ORCH CONTEXT] Starting research for chat_id={chat_id}, thread_id={thread_id}"
        )
        logger.debug(
            f"[ORCH CONTEXT] Query: '{query[:100]}...', use_web={use_web}, doc_ids={document_ids}"
        )

        # Fetch agent memory from Store
        memory_service = get_agent_memory_service()
        logger.info("[ORCH CONTEXT] Fetching agent memory from Store...")
        memory_context = await memory_service.build_memory_context(
            user_id=UUID(self.user_id),
            chat_id=chat_id,
            current_query=query,
        )

        memory_count = sum(len(v) for v in memory_context.values())
        logger.info(
            f"[ORCH CONTEXT] Loaded memory: {memory_count} total memories across {len(memory_context)} agents"
        )
        for agent_name, memories in memory_context.items():
            if memories:
                logger.debug(
                    f"[ORCH CONTEXT]   - {agent_name}: {len(memories)} memories"
                )

        try:
            # Create session linked to chat
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

            # Initialize state with memory context
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
                "memory_context": memory_context,  # Inject memory
            }

            # Execute graph (thread_id used for logging only)
            logger.info(f"[ORCH CONTEXT] Executing graph with thread_id={thread_id}")
            final_state = await self.graph.ainvoke(initial_state)

            # Extract results
            synthesis_result = final_state.get("synthesis_result", {})
            verification = final_state.get("verification", {})
            agent_timeline = final_state.get("agent_timeline", [])
            internal_sources = final_state.get("internal_sources", [])
            web_sources = final_state.get("web_sources", [])

            total_latency = int((time.perf_counter() - start_time) * 1000)
            all_sources = self._normalize_sources(internal_sources, web_sources)

            logger.info(
                f"[ORCH CONTEXT] Graph execution complete: {len(internal_sources)} internal sources, {len(web_sources)} web sources, latency={total_latency}ms"
            )

            answer = synthesis_result.get("answer", "")
            if not answer or not isinstance(answer, str):
                logger.warning(
                    "[ORCH CONTEXT] Invalid answer format, using fallback message"
                )
                answer = (
                    "I apologize, but I encountered an issue generating a response. "
                    "Please try rephrasing your question."
                )

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

            # Store agent memories
            logger.info(f"[ORCH CONTEXT] Storing agent memories for chat_id={chat_id}")
            await self._store_agent_memories(
                chat_id=chat_id,
                session_id=session_id,
                agent_timeline=agent_timeline,
            )

            # Log and update session
            self._log_agent_timeline(session_id, agent_timeline)
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
                    },
                }
            ).eq("id", session_id).execute()

            # Update chat title based on query
            from app.services.title_generator import generate_title_from_query

            new_title = generate_title_from_query(query)
            logger.info(f"[ORCH CONTEXT] Updating chat {chat_id} title to: {new_title}")

            try:
                self.supabase.table("chats").update(
                    {
                        "title": new_title,
                    }
                ).eq("id", str(chat_id)).execute()
                logger.info(f"[ORCH CONTEXT] Chat title updated successfully")
            except Exception as title_err:
                logger.error(f"[ORCH CONTEXT] Failed to update chat title: {title_err}")
                # Don't fail the request if title update fails

            logger.info(f"[ORCH CONTEXT] Complete! Latency: {total_latency}ms")
            return result

        except Exception as e:
            logger.error(f"[ORCH CONTEXT] Failed: {e}", exc_info=True)
            try:
                self.supabase.table("research_sessions").update(
                    {"status": "failed", "result": {"error": str(e)}}
                ).eq("id", session_id).execute()
            except Exception as db_err:
                logger.error(f"[ORCH CONTEXT] DB update failed: {db_err}")
            raise

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

        Combines memory-aware research with real-time streaming.
        """
        from app.agents.base import AgentInput
        from app.agents.planner import PlannerAgent
        from app.agents.retrieval import RetrievalAgent
        from app.agents.web_search import WebSearchAgent
        from app.agents.synthesis import SynthesisAgent
        from app.agents.critic import CriticAgent

        start_time = time.perf_counter()
        session_id = str(uuid4())

        # Fetch memory
        memory_service = get_agent_memory_service()
        memory_context = await memory_service.build_memory_context(
            user_id=UUID(self.user_id),
            chat_id=chat_id,
            current_query=query,
        )

        logger.info(f"[ORCH STREAM CONTEXT] Starting for chat {chat_id}")

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
            logger.error(f"[ORCH STREAM CONTEXT] Failed to create session: {e}")
            raise

        agent_timeline = []
        internal_sources = []
        web_sources = []
        synthesis_result = None
        verification = None

        try:
            # 1. Planning (with memory)
            yield {"type": "node_complete", "node": "planning", "status": "running"}
            planner = PlannerAgent()

            # Format planner memory
            planner_memory_prompt = memory_service.format_memory_for_prompt(
                "planner", memory_context.get("planner", [])
            )

            plan_input = AgentInput(
                query=query,
                constraints={
                    "use_web": use_web,
                    "memory_prompt": planner_memory_prompt,
                },
            )
            plan_output = await planner.run(plan_input)
            execution_plan = plan_output.result
            agent_timeline.append(plan_output.to_dict())
            yield {"type": "node_complete", "node": "planning", "status": "complete"}

            # 2. Retrieval (with memory)
            yield {"type": "node_complete", "node": "retrieval", "status": "running"}
            retrieval = RetrievalAgent(self.user_id)

            retrieval_memory_prompt = memory_service.format_memory_for_prompt(
                "retrieval", memory_context.get("retrieval", [])
            )

            retrieval_input = AgentInput(
                query=query,
                context={
                    "document_ids": document_ids,
                    "memory_prompt": retrieval_memory_prompt,
                },
                constraints=execution_plan.constraints if execution_plan else {},
            )
            retrieval_output = await retrieval.run(retrieval_input)
            internal_sources = retrieval_output.result
            agent_timeline.append(retrieval_output.to_dict())
            yield {"type": "node_complete", "node": "retrieval", "status": "complete"}
            yield {"type": "sources", "sources": internal_sources}

            # 3. Web Search (conditional)
            should_web_search = use_web
            if execution_plan and hasattr(execution_plan, "steps"):
                should_web_search = use_web and any(
                    step.tool == "web" for step in execution_plan.steps
                )

            if should_web_search:
                yield {
                    "type": "node_complete",
                    "node": "web_search",
                    "status": "running",
                }
                web_search = WebSearchAgent()
                web_input = AgentInput(
                    query=query,
                    constraints=execution_plan.constraints if execution_plan else {},
                )
                web_output = await web_search.run(web_input)
                web_sources = web_output.result
                agent_timeline.append(web_output.to_dict())
                yield {
                    "type": "node_complete",
                    "node": "web_search",
                    "status": "complete",
                }
                yield {"type": "sources", "sources": web_sources}

            # 4. Synthesis (with memory and streaming)
            yield {"type": "node_complete", "node": "synthesis", "status": "running"}
            synthesis = SynthesisAgent()

            synthesis_memory_prompt = memory_service.format_memory_for_prompt(
                "synthesis", memory_context.get("synthesis", [])
            )

            synthesis_input = AgentInput(
                query=query,
                context={
                    "internal_sources": internal_sources,
                    "web_sources": web_sources,
                    "memory_prompt": synthesis_memory_prompt,
                },
                constraints=execution_plan.constraints if execution_plan else {},
            )

            async for chunk in synthesis.run_stream(synthesis_input):
                if chunk.get("type") == "thought_chunk":
                    yield {"type": "thought_chunk", "content": chunk.get("content", "")}
                elif chunk.get("type") == "answer_chunk":
                    yield {"type": "answer_chunk", "content": chunk.get("content", "")}
                elif chunk.get("type") == "complete":
                    synthesis_output = chunk.get("output")
                    synthesis_result = (
                        synthesis_output.result if synthesis_output else {}
                    )
                    if synthesis_output:
                        agent_timeline.append(synthesis_output.to_dict())

            yield {"type": "node_complete", "node": "synthesis", "status": "complete"}

            all_sources = self._normalize_sources(internal_sources, web_sources)
            yield {"type": "sources", "sources": all_sources}

            # 5. Critic (with memory)
            yield {"type": "node_complete", "node": "critic", "status": "running"}
            verification = None
            try:
                critic = CriticAgent()

                critic_memory_prompt = memory_service.format_memory_for_prompt(
                    "critic", memory_context.get("critic", [])
                )

                critic_input = AgentInput(
                    query=query,
                    context={
                        "synthesis_result": synthesis_result,
                        "internal_sources": internal_sources,
                        "web_sources": web_sources,
                        "memory_prompt": critic_memory_prompt,
                    },
                )
                logger.info("[ORCH STREAM CONTEXT] Running critic with 20s timeout")
                critic_output = await asyncio.wait_for(
                    critic.run(critic_input), timeout=20.0
                )
                verification = critic_output.result
                agent_timeline.append(critic_output.to_dict())
                logger.info("[ORCH STREAM CONTEXT] Critic completed successfully")
                yield {"type": "node_complete", "node": "critic", "status": "complete"}
            except asyncio.TimeoutError:
                logger.warning("[ORCH STREAM CONTEXT] Critic timed out after 20s")
                verification = {
                    "verification_status": "timeout",
                    "issues": ["Verification timed out"],
                }
                yield {"type": "node_complete", "node": "critic", "status": "timeout"}
            except Exception as e:
                logger.error(f"[ORCH STREAM CONTEXT] Critic failed: {e}", exc_info=True)
                verification = {"verification_status": "error", "issues": [str(e)]}
                yield {"type": "node_complete", "node": "critic", "status": "error"}

            total_latency = int((time.perf_counter() - start_time) * 1000)

            # Store agent memories
            logger.info("[ORCH STREAM CONTEXT] Storing agent memories...")
            try:
                await self._store_agent_memories(
                    chat_id=chat_id,
                    session_id=session_id,
                    agent_timeline=agent_timeline,
                )
                logger.info("[ORCH STREAM CONTEXT] Agent memories stored successfully")
            except Exception as mem_err:
                logger.error(
                    f"[ORCH STREAM CONTEXT] Failed to store memories: {mem_err}",
                    exc_info=True,
                )
                # Continue anyway - don't block completion

            # Update session
            logger.info("[ORCH STREAM CONTEXT] Updating session in database...")
            try:
                self.supabase.table("research_sessions").update(
                    {
                        "status": "completed",
                        "result": {
                            "answer": synthesis_result.get("answer", "")
                            if synthesis_result
                            else "",
                            "sources": all_sources,
                            "verification": verification,
                            "confidence": (
                                verification.get("verification_status", "unknown")
                                if verification
                                else "unknown"
                            ),
                            "total_latency_ms": total_latency,
                            "query": query,
                            "session_id": session_id,
                        },
                    }
                ).eq("id", session_id).execute()
                logger.info("[ORCH STREAM CONTEXT] Session updated successfully")
            except Exception as db_err:
                logger.error(
                    f"[ORCH STREAM CONTEXT] Failed to update session: {db_err}",
                    exc_info=True,
                )

            self._log_agent_timeline(session_id, agent_timeline)

            # Update chat title based on query
            from app.services.title_generator import generate_title_from_query

            new_title = generate_title_from_query(query)
            logger.info(
                f"[ORCH STREAM CONTEXT] Updating chat {chat_id} title to: {new_title}"
            )

            try:
                self.supabase.table("chats").update(
                    {
                        "title": new_title,
                    }
                ).eq("id", str(chat_id)).execute()
                logger.info(f"[ORCH STREAM CONTEXT] Chat title updated successfully")

                # Emit SSE event for title update
                yield {
                    "type": "title_updated",
                    "title": new_title,
                    "chat_id": str(chat_id),
                }
            except Exception as title_err:
                logger.error(
                    f"[ORCH STREAM CONTEXT] Failed to update chat title: {title_err}"
                )
                # Don't fail the request if title update fails

            logger.info("[ORCH STREAM CONTEXT] Yielding final complete event")
            yield {
                "type": "complete",
                "session_id": session_id,
                "confidence": (
                    verification.get("verification_status", "unknown")
                    if verification
                    else "unknown"
                ),
                "total_latency_ms": total_latency,
                "sources": all_sources,
                "verification": verification,
            }
            logger.info("[ORCH STREAM CONTEXT] Stream complete!")

        except Exception as e:
            logger.error(f"[ORCH STREAM CONTEXT] Failed: {e}", exc_info=True)
            try:
                self.supabase.table("research_sessions").update(
                    {"status": "failed", "result": {"error": str(e)}}
                ).eq("id", session_id).execute()
            except Exception as db_err:
                logger.error(f"[ORCH STREAM CONTEXT] DB update failed: {db_err}")
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
                if hasattr(result, "subtasks"):
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
