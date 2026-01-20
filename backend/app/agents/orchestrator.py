"""Orchestrator - Coordinates agent execution for research queries."""

import time
from uuid import UUID, uuid4
from dataclasses import dataclass, field

from app.agents.base import AgentInput, AgentOutput
from app.agents.planner import PlannerAgent, ExecutionPlan
from app.agents.retrieval import RetrievalAgent
from app.agents.web_search import WebSearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.critic import CriticAgent
from app.core.database import get_supabase_client


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
        self.supabase = get_supabase_client()

        # Initialize agents
        self.planner = PlannerAgent()
        self.retrieval = RetrievalAgent(user_id)
        self.web_search = WebSearchAgent()
        self.synthesis = SynthesisAgent()
        self.critic = CriticAgent()

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
        self.supabase.table("research_sessions").insert(
            {
                "id": session_id,
                "user_id": self.user_id,
                "query": query,
                "status": "running",
            }
        ).execute()

        try:
            # 1. Plan the execution
            plan_input = AgentInput(
                query=query,
                constraints={"use_web": use_web},
            )
            plan_output = await self.planner.run(plan_input)
            timeline.append(plan_output.to_dict())
            self._log_agent(session_id, plan_output)

            plan: ExecutionPlan = plan_output.result

            # 2. Execute retrieval
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

            # 3. Execute web search if planned
            web_sources = []
            if use_web and any(s.tool == "web" for s in plan.steps):
                web_input = AgentInput(
                    query=query,
                    constraints=plan.constraints,
                )
                web_output = await self.web_search.run(web_input)
                timeline.append(web_output.to_dict())
                self._log_agent(session_id, web_output)
                web_sources = web_output.result

            # 4. Synthesize answer
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

            # 5. Verify answer
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
            self.supabase.table("research_sessions").update(
                {
                    "status": "completed",
                    "result": {
                        "answer": result.answer,
                        "confidence": result.confidence,
                    },
                }
            ).eq("id", session_id).execute()

            return result

        except Exception as e:
            # Update session with error
            self.supabase.table("research_sessions").update(
                {
                    "status": "failed",
                    "result": {"error": str(e)},
                }
            ).eq("id", session_id).execute()
            raise

    def _log_agent(self, session_id: str, output: AgentOutput):
        """Log agent execution to database."""
        self.supabase.table("agent_logs").insert(
            {
                "session_id": session_id,
                "agent_name": output.agent_name,
                "events": {
                    "result_summary": str(output.result)[:500],  # Truncate for storage
                    "metadata": output.metadata,
                },
                "latency_ms": output.latency_ms,
            }
        ).execute()
