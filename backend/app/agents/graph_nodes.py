"""LangGraph node functions that wrap existing agents.

Each node accepts (state, config) and dispatches custom events via
adispatch_custom_event so the orchestrator can stream them as SSE.
"""

import logging
from typing import Any

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from app.agents.base import AgentInput, AgentOutput
from app.agents.planner import PlannerAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.web_search import WebSearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.critic import CriticAgent
from app.agents.graph_state import ResearchState
from app.services.agent_memory import get_agent_memory_service

logger = logging.getLogger(__name__)


def _get_plan_constraints(state: ResearchState) -> dict[str, Any]:
    """Safely extract constraints from execution plan in state."""
    plan = state.get("execution_plan")
    if plan is not None:
        return plan.constraints
    return {}


def _get_memory_prompt(state: ResearchState, agent_name: str) -> str:
    """Format memory context for a specific agent from state."""
    memory_context = state.get("memory_context") or {}
    memories = memory_context.get(agent_name, [])
    if not memories:
        return ""
    memory_service = get_agent_memory_service()
    return memory_service.format_memory_for_prompt(agent_name, memories)


# Node: Planning
async def planning_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Analyze the query and create an execution plan.

    Returns updates to state including execution_plan and timeline entry.
    """
    logger.info(f"[GRAPH] Planning node for query: {state['query'][:50]}...")

    planner = PlannerAgent()

    memory_prompt = _get_memory_prompt(state, "planner")

    agent_input = AgentInput(
        query=state["query"],
        constraints={
            "use_web": state.get("use_web", True),
            "memory_prompt": memory_prompt,
        },
    )

    output = await planner.run(agent_input)

    return {
        "execution_plan": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Retrieval
async def retrieval_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Execute hybrid RAG search on internal documents.

    Dispatches a 'sources' custom event after search completes.
    Returns updates to state including internal_sources and timeline entry.
    """
    logger.info("[GRAPH] Retrieval node executing...")

    retrieval = RetrievalAgent(state["user_id"])

    memory_prompt = _get_memory_prompt(state, "retrieval")

    constraints = _get_plan_constraints(state)

    agent_input = AgentInput(
        query=state["query"],
        context={
            "document_ids": state.get("document_ids"),
            "memory_prompt": memory_prompt,
        },
        constraints=constraints,
    )

    output = await retrieval.run(agent_input)

    logger.info(f"[GRAPH] Retrieved {len(output.result)} sources")

    # Dispatch sources event for real-time streaming
    await adispatch_custom_event(
        "sources",
        {"sources": output.result},
        config=config,
    )

    return {
        "internal_sources": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Web Search
async def web_search_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Execute web search using Tavily API.

    Handles its own skip logic: returns empty results if web search
    is disabled or not needed by the plan. This enables parallel
    fan-out from planning (retrieval + web_search run concurrently).

    Dispatches a 'sources' custom event after search completes.
    Returns updates to state including web_sources and timeline entry.
    """
    # Check if web search should run
    if not state.get("use_web", True):
        logger.info("[GRAPH] Web search disabled by user, skipping")
        return {"web_sources": [], "agent_timeline": []}

    plan = state.get("execution_plan")
    if plan and not any(step.tool == "web" for step in plan.steps):
        logger.info("[GRAPH] Plan does not include web search, skipping")
        return {"web_sources": [], "agent_timeline": []}

    logger.info("[GRAPH] Web search node executing...")

    web_search = WebSearchAgent()

    # Get constraints from execution plan
    constraints = {}
    if plan:
        constraints = plan.constraints

    agent_input = AgentInput(
        query=state["query"],
        constraints=constraints,
    )

    output = await web_search.run(agent_input)

    logger.info(f"[GRAPH] Found {len(output.result)} web sources")

    # Dispatch sources event for real-time streaming
    if output.result:
        await adispatch_custom_event(
            "sources",
            {"sources": output.result},
            config=config,
        )

    return {
        "web_sources": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Synthesis
async def synthesis_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Combine all retrieved context into a grounded answer.

    Streams answer and thought chunks via adispatch_custom_event so the
    orchestrator can forward them as SSE events in real time.

    Returns updates to state including synthesis_result and timeline entry.
    """
    logger.info("[GRAPH] Synthesis node executing...")

    synthesis = SynthesisAgent()

    memory_prompt = _get_memory_prompt(state, "synthesis")

    constraints = _get_plan_constraints(state)

    context: dict[str, Any] = {
        "internal_sources": state.get("internal_sources", []),
        "web_sources": state.get("web_sources", []),
    }
    if memory_prompt:
        context["memory_prompt"] = memory_prompt

    agent_input = AgentInput(
        query=state["query"],
        context=context,
        constraints=constraints,
    )

    # Stream synthesis — dispatch chunks as custom events
    synthesis_output: AgentOutput | None = None

    async for chunk in synthesis.run_stream(agent_input):
        chunk_type = chunk.get("type")

        if chunk_type == "thought_chunk":
            await adispatch_custom_event(
                "thought_chunk",
                {"content": chunk.get("content", "")},
                config=config,
            )
        elif chunk_type == "answer_chunk":
            await adispatch_custom_event(
                "answer_chunk",
                {"content": chunk.get("content", "")},
                config=config,
            )
        elif chunk_type == "complete":
            output = chunk.get("output")
            if isinstance(output, AgentOutput):
                synthesis_output = output

    if synthesis_output:
        logger.info(
            f"[GRAPH] Synthesis complete with confidence: "
            f"{synthesis_output.result.get('confidence', 'unknown')}"
        )
        return {
            "synthesis_result": synthesis_output.result,
            "agent_timeline": [synthesis_output.to_dict()],
        }

    logger.warning("[GRAPH] Synthesis completed without output")
    return {
        "synthesis_result": {},
        "agent_timeline": [],
    }


# Node: Critic/Verification
async def critic_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Verify the synthesized answer against sources.

    Runs inline (not in background) so the feedback loop works.
    Returns updates to state including verification, needs_refinement flag,
    and timeline entry.
    """
    logger.info("[GRAPH] Critic node executing...")

    critic = CriticAgent()

    agent_input = AgentInput(
        query=state["query"],
        context={
            "synthesis_result": state.get("synthesis_result"),
            "internal_sources": state.get("internal_sources", []),
            "web_sources": state.get("web_sources", []),
        },
    )

    output = await critic.run(agent_input)
    verification = output.result

    # Determine if we need refinement
    current_iteration = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 2)

    # Check confidence and verification status
    confidence = verification.get("verification_status", "unknown")
    needs_refinement = False

    if current_iteration < max_iterations:
        # If confidence is low or verification failed, trigger refinement
        if confidence in ["low", "failed", "unverified"]:
            needs_refinement = True
            logger.info(f"[GRAPH] Low confidence ({confidence}), triggering refinement")

    logger.info(
        f"[GRAPH] Verification complete: {confidence}, refinement needed: {needs_refinement}"
    )

    return {
        "verification": verification,
        "needs_refinement": needs_refinement,
        "iteration_count": current_iteration + 1,
        "agent_timeline": [output.to_dict()],
    }


# Conditional edge: Should we refine the answer?
def should_refine(state: ResearchState) -> str:
    """
    Decide whether to refine the answer or finish.

    Returns "synthesis" to refine, or "end" to finish.
    """
    if state.get("needs_refinement", False):
        logger.info("[GRAPH] Refinement needed, looping back to synthesis")
        return "synthesis"

    logger.info("[GRAPH] Answer verified, finishing")
    return "end"
