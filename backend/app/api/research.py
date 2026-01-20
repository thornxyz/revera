"""Research API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID

from app.agents.orchestrator import Orchestrator


router = APIRouter()


class ResearchRequest(BaseModel):
    """Request body for research query."""

    query: str
    use_web: bool = True
    document_ids: list[str] | None = None


class ResearchResponse(BaseModel):
    """Response for research query."""

    session_id: str
    query: str
    answer: str
    sources: list[dict]
    verification: dict
    confidence: str
    total_latency_ms: int


class AgentTimelineResponse(BaseModel):
    """Response with agent execution timeline."""

    session_id: str
    timeline: list[dict]


# TODO: Replace with actual auth dependency
async def get_current_user_id() -> str:
    """Placeholder for auth - returns mock user ID."""
    return "00000000-0000-0000-0000-000000000001"


@router.post("/query", response_model=ResearchResponse)
async def create_research_query(
    request: ResearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Execute a research query.

    This endpoint:
    1. Plans the research approach
    2. Retrieves relevant context from documents
    3. Optionally searches the web
    4. Synthesizes an answer with citations
    5. Verifies the answer against sources
    """
    try:
        orchestrator = Orchestrator(user_id)
        result = await orchestrator.research(
            query=request.query,
            use_web=request.use_web,
            document_ids=request.document_ids,
        )

        return ResearchResponse(
            session_id=result.session_id,
            query=result.query,
            answer=result.answer,
            sources=result.sources,
            verification=result.verification,
            confidence=result.confidence,
            total_latency_ms=result.total_latency_ms,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/timeline", response_model=AgentTimelineResponse)
async def get_session_timeline(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the agent execution timeline for a session."""
    from app.core.database import get_supabase_client

    supabase = get_supabase_client()

    # Verify session belongs to user
    session = (
        supabase.table("research_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not session.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get agent logs
    logs = (
        supabase.table("agent_logs")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )

    return AgentTimelineResponse(
        session_id=session_id,
        timeline=[
            {
                "agent": log["agent_name"],
                "events": log["events"],
                "latency_ms": log["latency_ms"],
                "timestamp": log["created_at"],
            }
            for log in logs.data
        ],
    )
