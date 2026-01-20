"""Research API routes."""

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import Orchestrator
from app.core.auth import get_current_user_id

logger = logging.getLogger(__name__)

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
    logger.info(f"[RESEARCH] Starting query: {request.query[:50]}...")
    logger.info(f"[RESEARCH] User ID: {user_id}")
    logger.info(
        f"[RESEARCH] Use web: {request.use_web}, Doc IDs: {request.document_ids}"
    )

    try:
        logger.info("[RESEARCH] Creating orchestrator...")
        orchestrator = Orchestrator(user_id)

        logger.info("[RESEARCH] Running research...")
        result = await orchestrator.research(
            query=request.query,
            use_web=request.use_web,
            document_ids=request.document_ids,
        )

        logger.info(
            f"[RESEARCH] Complete! Session: {result.session_id}, Latency: {result.total_latency_ms}ms"
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
        logger.error(f"[RESEARCH] ERROR: {str(e)}")
        logger.error(f"[RESEARCH] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/timeline", response_model=AgentTimelineResponse)
async def get_session_timeline(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the agent execution timeline for a session."""
    from app.core.database import get_supabase_client

    logger.info(f"[TIMELINE] Getting timeline for session: {session_id}")

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
