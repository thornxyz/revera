"""LangGraph node functions that wrap existing agents."""

import logging
import time
from uuid import UUID

from app.agents.base import AgentInput
from app.agents.planner import PlannerAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.web_search import WebSearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.critic import CriticAgent
from app.agents.graph_state import ResearchState

logger = logging.getLogger(__name__)


# Node: Planning
async def planning_node(state: ResearchState) -> dict:
    """
    Analyze the query and create an execution plan.

    Returns updates to state including execution_plan and timeline entry.
    """
    logger.info(f"[GRAPH] Planning node for query: {state['query'][:50]}...")

    planner = PlannerAgent()

    agent_input = AgentInput(
        query=state["query"],
        constraints={"use_web": state["use_web"]},
    )

    output = await planner.run(agent_input)

    return {
        "execution_plan": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Retrieval
async def retrieval_node(state: ResearchState) -> dict:
    """
    Execute hybrid RAG search on internal documents.

    Returns updates to state including internal_sources and timeline entry.
    """
    logger.info("[GRAPH] Retrieval node executing...")

    retrieval = RetrievalAgent(state["user_id"])

    # Get constraints from execution plan
    constraints = {}
    if state.get("execution_plan"):
        constraints = state["execution_plan"].constraints

    agent_input = AgentInput(
        query=state["query"],
        context={"document_ids": state.get("document_ids")},
        constraints=constraints,
    )

    output = await retrieval.run(agent_input)

    logger.info(f"[GRAPH] Retrieved {len(output.result)} sources")

    return {
        "internal_sources": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Web Search
async def web_search_node(state: ResearchState) -> dict:
    """
    Execute web search using Tavily API.

    Returns updates to state including web_sources and timeline entry.
    """
    logger.info("[GRAPH] Web search node executing...")

    web_search = WebSearchAgent()

    # Get constraints from execution plan
    constraints = {}
    if state.get("execution_plan"):
        constraints = state["execution_plan"].constraints

    agent_input = AgentInput(
        query=state["query"],
        constraints=constraints,
    )

    output = await web_search.run(agent_input)

    logger.info(f"[GRAPH] Found {len(output.result)} web sources")

    return {
        "web_sources": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Synthesis
async def synthesis_node(state: ResearchState) -> dict:
    """
    Combine all retrieved context into a grounded answer.

    Returns updates to state including synthesis_result and timeline entry.
    """
    logger.info("[GRAPH] Synthesis node executing...")

    synthesis = SynthesisAgent()

    # Get constraints from execution plan
    constraints = {}
    if state.get("execution_plan"):
        constraints = state["execution_plan"].constraints

    agent_input = AgentInput(
        query=state["query"],
        context={
            "internal_sources": state.get("internal_sources", []),
            "web_sources": state.get("web_sources", []),
        },
        constraints=constraints,
    )

    output = await synthesis.run(agent_input)

    logger.info(
        f"[GRAPH] Synthesis complete with confidence: {output.result.get('confidence', 'unknown')}"
    )

    return {
        "synthesis_result": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Critic/Verification
async def critic_node(state: ResearchState) -> dict:
    """
    Verify the synthesized answer against sources.

    Returns updates to state including verification, needs_refinement flag, and timeline entry.
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


# Conditional edge: Should we run web search?
def should_run_web_search(state: ResearchState) -> str:
    """
    Decide whether to run web search based on plan and user preference.

    Returns the next node name: "web_search" or "synthesis"
    """
    if not state.get("use_web", True):
        logger.info("[GRAPH] Web search disabled by user")
        return "synthesis"

    plan = state.get("execution_plan")
    if plan and any(step.tool == "web" for step in plan.steps):
        logger.info("[GRAPH] Plan includes web search")
        return "web_search"

    logger.info("[GRAPH] No web search needed")
    return "synthesis"


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
