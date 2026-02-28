"""LangGraph workflow for research orchestration."""

import logging
from langgraph.graph import StateGraph, END

from app.agents.graph_state import ResearchState
from app.agents.graph_nodes import (
    planning_node,
    retrieval_node,
    web_search_node,
    image_gen_node,
    synthesis_node,
    critic_node,
    should_refine,
)

logger = logging.getLogger(__name__)


def build_research_graph(async_critic: bool = False) -> StateGraph:
    """
    Build the LangGraph research workflow with parallel execution and feedback loops.

    Graph structure:

        START
          |
        planning
          /    \\
     retrieval  web_search  image_gen   (parallel fan-out — all run concurrently)
          \\    //          /
        synthesis                  (fan-in — waits for all three)
            |
          critic (if async_critic=False)
          /    \\
     synthesis  END           (conditional: refine or finish)
     (loop)

    If async_critic=True, synthesis goes directly to END and critic runs in background.

    Key features:
    - Parallel execution: retrieval + web_search + image_gen run concurrently after planning
    - Self-managing skip: web_search and image_gen return empty if disabled/not in plan
    - Feedback loop: critic can send back to synthesis for refinement (max 2 iterations)
    - Streaming: synthesis dispatches answer/thought chunks via custom events
    - State management: shared ResearchState across all nodes
    - Async critic: optionally skip critic in graph for background execution
    """

    # Create the graph
    workflow = StateGraph(ResearchState)

    # Add nodes
    logger.info(f"[GRAPH] Building research graph (async_critic={async_critic})...")
    workflow.add_node("planning", planning_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("image_gen", image_gen_node)
    workflow.add_node("synthesis", synthesis_node)

    if not async_critic:
        workflow.add_node("critic", critic_node)

    # Set entry point
    workflow.set_entry_point("planning")

    # Parallel fan-out: planning feeds retrieval, web_search, AND image_gen
    # LangGraph schedules all concurrently since none depend on each other
    workflow.add_edge("planning", "retrieval")
    workflow.add_edge("planning", "web_search")
    workflow.add_edge("planning", "image_gen")

    # Fan-in: retrieval, web_search, and image_gen all feed into synthesis
    # LangGraph waits for ALL three to complete before running synthesis
    workflow.add_edge("retrieval", "synthesis")
    workflow.add_edge("web_search", "synthesis")
    workflow.add_edge("image_gen", "synthesis")

    if async_critic:
        # Skip critic in graph - it runs in background
        workflow.add_edge("synthesis", END)
    else:
        # Synthesis always goes to critic
        workflow.add_edge("synthesis", "critic")

        # Critic decides whether to refine or end
        workflow.add_conditional_edges(
            "critic",
            should_refine,
            {
                "synthesis": "synthesis",  # Loop back for refinement
                "end": END,
            },
        )

    logger.info("[GRAPH] Research graph built successfully")

    return workflow


def compile_research_graph(async_critic: bool = False):
    """
    Compile the research graph into an executable workflow.

    Args:
        async_critic: If True, skip critic in graph for background execution

    Returns a compiled graph that can be invoked with initial state.
    """
    workflow = build_research_graph(async_critic=async_critic)
    compiled = workflow.compile()
    logger.info(f"[GRAPH] Research graph compiled (async_critic={async_critic})")
    return compiled
