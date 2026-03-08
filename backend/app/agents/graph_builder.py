"""LangGraph workflow for research orchestration."""

import logging
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.graph_state import ResearchState
from app.agents.graph_nodes import (
    router_node,
    planning_node,
    retrieval_node,
    web_search_node,
    image_gen_node,
    synthesis_node,
    critic_node,
    route_after_router,
    route_after_synthesis,
    should_refine,
)

logger = logging.getLogger(__name__)


def build_research_graph(async_critic: bool = False) -> StateGraph:
    """
    Build the LangGraph research workflow with tiered query routing.

    Graph structure:

        START
          |
        router ──────────────────────────────────────────────────┐
          |                                                       |
          |─[RESEARCH]──► planning                               |
          |                 |  \\  \\                             |
          |             retrieval  web_search  image_gen          |
          |                 \\   /     /                          |
          |               synthesis ◄────────────────────────────┤
          |                                                       |
          |─[FOCUSED/rag]──► focused_retrieval ──► synthesis      |
          |─[FOCUSED/web]──► focused_web_search ─► synthesis      |
          └─[DIRECT]───────────────────────────► synthesis        |
                                                    |             |
                                             [async_critic=False] |
                                               route_after_synthesis
                                               /              \\
                                            critic            END
                                           /      \\
                                       synthesis    END  (should_refine loop)

    Tier behaviour:
    - DIRECT:   No retrieval. Synthesis answers from LLM knowledge + memory.
    - FOCUSED:  One retrieval node (rag OR web). No planning. No critic.
    - RESEARCH: Full pipeline unchanged. Planning → parallel fan-out → synthesis → critic.

    FOCUSED paths use alias nodes (focused_retrieval, focused_web_search) that run
    the same underlying functions as retrieval_node / web_search_node but have
    independent edges to synthesis, avoiding the RESEARCH fan-in join deadlock.
    """

    workflow = StateGraph(ResearchState)

    # --- Nodes ---
    logger.info(
        f"[GRAPH] Building tiered research graph (async_critic={async_critic})..."
    )

    workflow.add_node("router", router_node)
    workflow.add_node("planning", planning_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("image_gen", image_gen_node)
    # Alias nodes for FOCUSED paths — same functions, independent fan-in semantics
    workflow.add_node("focused_retrieval", retrieval_node)
    workflow.add_node("focused_web_search", web_search_node)
    workflow.add_node("synthesis", synthesis_node)

    if not async_critic:
        workflow.add_node("critic", critic_node)

    # --- Entry point ---
    workflow.set_entry_point("router")

    # --- Router branches into three paths ---
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "planning": "planning",
            "focused_retrieval": "focused_retrieval",
            "focused_web_search": "focused_web_search",
            "synthesis": "synthesis",
        },
    )

    # --- RESEARCH path: planning → parallel fan-out → synthesis ---
    workflow.add_edge("planning", "retrieval")
    workflow.add_edge("planning", "web_search")
    workflow.add_edge("planning", "image_gen")
    # Fan-in: LangGraph waits for all three before firing synthesis
    workflow.add_edge("retrieval", "synthesis")
    workflow.add_edge("web_search", "synthesis")
    workflow.add_edge("image_gen", "synthesis")

    # --- FOCUSED paths: single node → synthesis (independent, no fan-in wait) ---
    workflow.add_edge("focused_retrieval", "synthesis")
    workflow.add_edge("focused_web_search", "synthesis")

    # --- After synthesis: critic only for RESEARCH tier ---
    if async_critic:
        workflow.add_edge("synthesis", END)
    else:
        workflow.add_conditional_edges(
            "synthesis",
            route_after_synthesis,
            {
                "critic": "critic",
                "end": END,
            },
        )
        # Critic feedback loop (RESEARCH only)
        workflow.add_conditional_edges(
            "critic",
            should_refine,
            {
                "synthesis": "synthesis",
                "end": END,
            },
        )

    logger.info("[GRAPH] Tiered research graph built successfully")
    return workflow


def compile_research_graph(
    async_critic: bool = False,
    checkpointer: Any = None,
):
    """
    Compile the research graph into an executable workflow.

    Args:
        async_critic: If True, skip critic in graph for background execution
        checkpointer: Optional LangGraph checkpointer for state persistence.
                      When provided, graph state is saved per thread_id,
                      enabling multi-turn conversations to survive restarts.

    Returns a compiled graph that can be invoked with initial state.
    """
    workflow = build_research_graph(async_critic=async_critic)
    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info(
        f"[GRAPH] Research graph compiled (async_critic={async_critic}, "
        f"checkpointer={'enabled' if checkpointer else 'disabled'})"
    )
    return compiled
