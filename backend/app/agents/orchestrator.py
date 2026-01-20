"""Orchestrator - Coordinates agent execution for research queries."""

import logging
import time
from uuid import uuid4
from dataclasses import dataclass

from app.agents.base import AgentInput, AgentOutput
from app.agents.planner import PlannerAgent, ExecutionPlan
from app.agents.retrieval import RetrievalAgent
from app.agents.web_search import WebSearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.critic import CriticAgent
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
    Central controller that orchestrates agent execution.

    Flow:
    1. Planner creates execution plan
    2. Execute tools in order (RAG, Web, etc.)
    3. Synthesis produces answer
    4. Critic verifies
    5. Log everything
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        logger.info(f"[ORCH] Initializing orchestrator for user: {user_id}")
        self.supabase = get_supabase_client()

        # Initialize agents
        logger.info("[ORCH] Initializing agents...")
        self.planner = PlannerAgent()
        self.retrieval = RetrievalAgent(user_id)
        self.web_search = WebSearchAgent()
        self.synthesis = SynthesisAgent()
        self.critic = CriticAgent()
        logger.info("[ORCH] Agents initialized")

    async def research(
        self,
        query: str,
        use_web: bool = True,
        document_ids: list[str] | None = None,
    ) -> ResearchResult:
        """Execute a complete research query."""
        start_time = time.perf_counter()
        timeline = []

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
            # 1. Plan the execution
            logger.info("[ORCH] Step 1: Planning...")
            plan_input = AgentInput(
                query=query,
                constraints={"use_web": use_web},
            )
            plan_output = await self.planner.run(plan_input)
            timeline.append(plan_output.to_dict())
            self._log_agent(session_id, plan_output)
            logger.info(f"[ORCH] Planning complete: {plan_output.latency_ms}ms")

            plan: ExecutionPlan = plan_output.result

            # 2. Execute retrieval
            logger.info("[ORCH] Step 2: Retrieval...")
            internal_sources = []
            retrieval_input = AgentInput(
                query=query,
                context={"document_ids": document_ids},
                constraints=plan.constraints,
            )
            retrieval_output = await self.retrieval.run(retrieval_input)
            timeline.append(retrieval_output.to_dict())
            self._log_agent(session_id, retrieval_output)
            internal_sources = retrieval_output.result
            logger.info(
                f"[ORCH] Retrieval complete: {len(internal_sources)} sources, {retrieval_output.latency_ms}ms"
            )

            # 3. Execute web search if planned
            web_sources = []
            if use_web and any(s.tool == "web" for s in plan.steps):
                logger.info("[ORCH] Step 3: Web search...")
                web_input = AgentInput(
                    query=query,
                    constraints=plan.constraints,
                )
                web_output = await self.web_search.run(web_input)
                timeline.append(web_output.to_dict())
                self._log_agent(session_id, web_output)
                web_sources = web_output.result
                logger.info(
                    f"[ORCH] Web search complete: {len(web_sources)} sources, {web_output.latency_ms}ms"
                )
            else:
                logger.info("[ORCH] Step 3: Skipping web search")

            # 4. Synthesize answer
            logger.info("[ORCH] Step 4: Synthesis...")
            synthesis_input = AgentInput(
                query=query,
                context={
                    "internal_sources": internal_sources,
                    "web_sources": web_sources,
                },
                constraints=plan.constraints,
            )
            synthesis_output = await self.synthesis.run(synthesis_input)
            timeline.append(synthesis_output.to_dict())
            self._log_agent(session_id, synthesis_output)
            synthesis_result = synthesis_output.result
            logger.info(f"[ORCH] Synthesis complete: {synthesis_output.latency_ms}ms")

            # 5. Verify answer
            logger.info("[ORCH] Step 5: Verification...")
            critic_input = AgentInput(
                query=query,
                context={
                    "synthesis_result": synthesis_result,
                    "internal_sources": internal_sources,
                    "web_sources": web_sources,
                },
            )
            critic_output = await self.critic.run(critic_input)
            timeline.append(critic_output.to_dict())
            self._log_agent(session_id, critic_output)
            verification = critic_output.result
            logger.info(f"[ORCH] Verification complete: {critic_output.latency_ms}ms")

            # Build final result
            total_latency = int((time.perf_counter() - start_time) * 1000)

            # Combine all sources
            all_sources = []
            for s in internal_sources:
                all_sources.append({**s, "type": "internal"})
            for s in web_sources:
                all_sources.append({**s, "type": "web"})

            result = ResearchResult(
                session_id=session_id,
                query=query,
                answer=synthesis_result.get("answer", ""),
                sources=all_sources,
                verification=verification,
                agent_timeline=timeline,
                total_latency_ms=total_latency,
                confidence=verification.get("verification_status", "unknown"),
            )

            # Update session status
            logger.info("[ORCH] Updating session status to completed...")
            self.supabase.table("research_sessions").update(
                {
                    "status": "completed",
                    "result": {
                        "answer": result.answer,
                        "confidence": result.confidence,
                    },
                }
            ).eq("id", session_id).execute()

            logger.info(f"[ORCH] Research complete! Total: {total_latency}ms")
            return result

        except Exception as e:
            logger.error(f"[ORCH] Research failed: {e}")
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

    def _log_agent(self, session_id: str, output: AgentOutput):
        """Log agent execution to database."""
        try:
            self.supabase.table("agent_logs").insert(
                {
                    "session_id": session_id,
                    "agent_name": output.agent_name,
                    "events": {
                        "result_summary": str(output.result)[:500],
                        "metadata": output.metadata,
                    },
                    "latency_ms": output.latency_ms,
                }
            ).execute()
        except Exception as e:
            logger.warning(f"[ORCH] Failed to log agent {output.agent_name}: {e}")
