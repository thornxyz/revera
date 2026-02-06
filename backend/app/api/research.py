"""Research API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentTimelineResponse(BaseModel):
    """Response with agent execution timeline."""

    session_id: str
    timeline: list[dict]


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
