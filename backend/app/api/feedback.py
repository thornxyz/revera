"""Feedback API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from uuid import UUID

from app.core.database import get_supabase_client


router = APIRouter()


class FeedbackRequest(BaseModel):
    """Request body for submitting feedback."""

    session_id: str
    rating: int = Field(ge=1, le=5, description="Rating from 1-5")
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Response for feedback submission."""

    id: str
    status: str


# TODO: Replace with actual auth dependency
async def get_current_user_id() -> str:
    """Placeholder for auth - returns mock user ID."""
    return "00000000-0000-0000-0000-000000000001"


@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Submit feedback for a research session.

    This helps improve retrieval and answer quality over time.
    """
    supabase = get_supabase_client()

    # Verify session exists and belongs to user
    session = (
        supabase.table("research_sessions")
        .select("id")
        .eq("id", request.session_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not session.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Insert feedback
    result = (
        supabase.table("feedback")
        .insert(
            {
                "session_id": request.session_id,
                "user_id": user_id,
                "rating": request.rating,
                "comment": request.comment,
            }
        )
        .execute()
    )

    return FeedbackResponse(
        id=result.data[0]["id"],
        status="submitted",
    )
