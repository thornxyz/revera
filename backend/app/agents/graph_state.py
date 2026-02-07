"""LangGraph state schema for research workflow."""

from typing import Annotated, TypedDict
from operator import add

from app.agents.agent_models import ExecutionPlan


class ImageContextState(TypedDict):
    """Image context for multimodal processing."""

    document_id: str
    filename: str
    storage_path: str
    description: str
    mime_type: str


class ResearchState(TypedDict):
    """
    State that flows through the LangGraph research workflow.

    This replaces the manual context dictionary passing in the old orchestrator.
    Each node reads from and writes to this shared state.
    """

    # Core inputs
    query: str
    user_id: str
    session_id: str
    use_web: bool
    document_ids: list[str] | None

    # Chat context (set by orchestrator before graph invocation)
    chat_id: str | None
    thread_id: str | None

    # Planning outputs
    execution_plan: ExecutionPlan | None

    # Retrieval outputs
    internal_sources: list[dict]

    # Web search outputs
    web_sources: list[dict]
    tavily_answer: str | None  # Quick AI-generated answer from Tavily

    # Image context for multimodal synthesis
    image_contexts: list[ImageContextState]

    # Synthesis outputs
    synthesis_result: dict | None

    # Verification outputs
    verification: dict | None

    # Timeline tracking - use Annotated with 'add' operator to append
    # This allows each node to add its output to the timeline
    agent_timeline: Annotated[list[dict], add]

    # Iteration control
    iteration_count: int
    needs_refinement: bool
    max_iterations: int

    # Memory context for chat-based research (populated before graph invocation)
    memory_context: dict[str, list[dict]] | None
