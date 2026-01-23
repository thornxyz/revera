"""API endpoints for managing research session history."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

from app.core.auth import get_current_user_id
from app.core.database import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionSummary(BaseModel):
    """Summary of a research session."""
    id: str
    query: str
    status: str
    created_at: datetime


class SessionDetail(BaseModel):
    """Detailed view of a research session."""
    id: str
    query: str
    status: str
    created_at: datetime
    result: Optional[Any] = None


@router.get("/", response_model=List[SessionSummary])
async def list_sessions(
    user_id: str = Depends(get_current_user_id),
):
    """List all research sessions for the current user."""
    supabase = get_supabase_client()
    
    response = (
        supabase.table("research_sessions")
        .select("id, query, status, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    
    return [SessionSummary(**session) for session in response.data]


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get full details of a specific session."""
    supabase = get_supabase_client()
    
    response = (
        supabase.table("research_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return SessionDetail(**response.data)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a research session."""
    supabase = get_supabase_client()
    
    # First check if exists and belongs to user
    check = (
        supabase.table("research_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    
    if not check.data:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Delete (cascade will handle logs and feedback)
    supabase.table("research_sessions").delete().eq("id", session_id).execute()
    
    return {"message": "Session deleted"}
