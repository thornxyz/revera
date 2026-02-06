"""Chats API routes for multi-turn conversations."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.core.database import get_supabase_client
from app.core.utils import sanitize_for_postgres
from app.models.schemas import Chat, ChatCreate, ChatWithPreview, Message
from app.services.agent_memory import get_agent_memory_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================
# Request/Response Models
# ============================================


class ChatQueryRequest(BaseModel):
    """Request body for sending a query in a chat."""

    query: str
    use_web: bool = True
    document_ids: list[str] | None = None


# ============================================
# Chat CRUD Endpoints
# ============================================


@router.get("/", response_model=list[ChatWithPreview])
async def list_chats(
    user_id: str = Depends(get_current_user_id),
):
    """
    List all chats for the current user.

    Returns chats with last message preview and message count,
    sorted by most recently updated.
    """
    logger.info(f"[CHATS] Listing chats for user_id={user_id}")
    supabase = get_supabase_client()

    try:
        # Get all chats for user
        chats_response = (
            supabase.table("chats")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )

        if not chats_response.data:
            logger.info(f"[CHATS] No chats found for user_id={user_id}")
            return []

        logger.info(
            f"[CHATS] Found {len(chats_response.data)} chats for user_id={user_id}"
        )

        result = []

        for chat in chats_response.data:
            chat_id = chat["id"]
            logger.debug(f"[CHATS] Processing chat_id={chat_id}")

            # Get message count
            messages_response = (
                supabase.table("messages")
                .select("id", count="exact")
                .eq("chat_id", chat_id)
                .execute()
            )
            message_count = messages_response.count or 0

            # Get last message for preview
            last_message_response = (
                supabase.table("messages")
                .select("query")
                .eq("chat_id", chat_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            last_message_preview = None
            if last_message_response.data:
                query = last_message_response.data[0]["query"]
                # Truncate long queries
                last_message_preview = query[:80] + "..." if len(query) > 80 else query

            result.append(
                ChatWithPreview(
                    id=chat_id,
                    user_id=chat["user_id"],
                    title=chat.get("title"),
                    thread_id=chat.get("thread_id"),
                    created_at=chat["created_at"],
                    updated_at=chat["updated_at"],
                    last_message_preview=last_message_preview,
                    message_count=message_count,
                )
            )

        logger.info(f"[CHATS] Successfully retrieved {len(result)} chats with previews")
        return result

    except Exception as e:
        logger.error(
            f"[CHATS] Error listing chats for user_id={user_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to list chats: {str(e)}")


@router.post("/", response_model=Chat)
async def create_chat(
    chat_data: ChatCreate | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a new chat.

    Optionally provide a title, or it will be auto-generated from the first message.
    """
    import uuid

    logger.info(
        f"[CHATS] Creating new chat for user_id={user_id}, title={chat_data.title if chat_data else 'None'}"
    )

    try:
        supabase = get_supabase_client()

        chat_id = uuid.uuid4()
        thread_id = f"chat-{chat_id}"

        logger.debug(f"[CHATS] Generated chat_id={chat_id}, thread_id={thread_id}")

        new_chat = {
            "id": str(chat_id),
            "user_id": user_id,
            "title": chat_data.title if chat_data else None,
            "thread_id": thread_id,
        }

        response = supabase.table("chats").insert(new_chat).execute()

        if not response.data:
            logger.error("[CHATS] Failed to create chat: No data returned from insert")
            raise HTTPException(status_code=500, detail="Failed to create chat")

        created_chat = response.data[0]
        logger.info(f"[CHATS] Successfully created chat_id={created_chat['id']}")

        return Chat(
            id=created_chat["id"],
            user_id=created_chat["user_id"],
            title=created_chat.get("title"),
            thread_id=created_chat.get("thread_id"),
            created_at=created_chat["created_at"],
            updated_at=created_chat["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CHATS] Error creating chat for user_id={user_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to create chat: {str(e)}")


@router.get("/{chat_id}", response_model=Chat)
async def get_chat(
    chat_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details of a specific chat."""
    logger.info(f"[CHATS] Getting chat_id={chat_id} for user_id={user_id}")

    try:
        supabase = get_supabase_client()

        response = (
            supabase.table("chats")
            .select("*")
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not response.data:
            logger.warning(
                f"[CHATS] Chat not found: chat_id={chat_id}, user_id={user_id}"
            )
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = response.data
        logger.info(
            f"[CHATS] Successfully retrieved chat_id={chat_id}, title={chat.get('title')}"
        )

        return Chat(
            id=chat["id"],
            user_id=chat["user_id"],
            title=chat.get("title"),
            thread_id=chat.get("thread_id"),
            created_at=chat["created_at"],
            updated_at=chat["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CHATS] Error getting chat_id={chat_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to get chat: {str(e)}")


@router.put("/{chat_id}", response_model=Chat)
async def update_chat(
    chat_id: str,
    chat_data: ChatCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Update chat details (e.g., rename title)."""
    supabase = get_supabase_client()

    # Verify ownership
    check = (
        supabase.table("chats")
        .select("id")
        .eq("id", chat_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not check.data:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Update
    response = (
        supabase.table("chats")
        .update({"title": chat_data.title})
        .eq("id", chat_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to update chat")

    updated = response.data[0]

    return Chat(
        id=updated["id"],
        user_id=updated["user_id"],
        title=updated.get("title"),
        thread_id=updated.get("thread_id"),
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
    )


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete a chat and ALL associated data.

    This comprehensively deletes:
    - Agent memories (InMemoryStore - episodic/semantic)
    - Document embeddings (Qdrant vectors)
    - Documents and chunks (database + Qdrant)
    - Research sessions and agent logs
    - Messages
    - Chat record

    Returns deletion statistics for verification.
    """
    from app.services.chat_cleanup import get_cleanup_service

    try:
        cleanup_service = get_cleanup_service()
        stats = await cleanup_service.delete_chat_completely(chat_id, user_id)
        return {
            "message": "Chat and all associated data deleted successfully",
            "stats": stats,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[DELETE_CHAT] Error deleting chat {chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")


# ============================================
# Message Endpoints
# ============================================


@router.get("/{chat_id}/messages", response_model=list[Message])
async def get_chat_messages(
    chat_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get all messages for a chat."""
    supabase = get_supabase_client()

    # Verify chat ownership
    chat_check = (
        supabase.table("chats")
        .select("id")
        .eq("id", chat_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chat_check.data:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get messages
    messages_response = (
        supabase.table("messages")
        .select("*")
        .eq("chat_id", chat_id)
        .order("created_at")
        .execute()
    )

    if not messages_response.data:
        return []

    return [
        Message(
            id=msg["id"],
            chat_id=msg["chat_id"],
            session_id=msg.get("session_id"),
            query=msg["query"],
            answer=msg.get("answer"),
            role=msg["role"],
            sources=msg.get("sources", []),
            verification=msg.get("verification"),
            confidence=msg.get("confidence"),
            thinking=msg.get("thinking"),
            agent_timeline=msg.get("agent_timeline"),
            created_at=msg["created_at"],
        )
        for msg in messages_response.data
    ]


@router.get("/{chat_id}/messages/{message_id}/verification")
async def get_message_verification(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get verification status for a message.

    Used for polling when critic completes in background.
    Returns 202 if still pending, 200 when complete.
    """
    from fastapi.responses import JSONResponse

    supabase = get_supabase_client()

    # Verify chat ownership
    chat_check = (
        supabase.table("chats")
        .select("id")
        .eq("id", chat_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chat_check.data:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get message
    message_response = (
        supabase.table("messages")
        .select("verification, confidence")
        .eq("id", message_id)
        .eq("chat_id", chat_id)
        .single()
        .execute()
    )

    if not message_response.data:
        raise HTTPException(status_code=404, detail="Message not found")

    message = message_response.data
    confidence = message.get("confidence", "unknown")

    # Return 202 if still pending, 200 when complete
    status_code = 202 if confidence == "pending" else 200

    return JSONResponse(
        status_code=status_code,
        content={
            "confidence": confidence,
            "verification": message.get("verification"),
            "status": "pending" if confidence == "pending" else "complete",
        },
    )


# ============================================
# Query Endpoints (Research within a chat)
# ============================================


@router.post("/{chat_id}/query/stream")
async def send_chat_query_stream(
    chat_id: str,
    request: ChatQueryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Send a query within a chat with streaming responses.

    Uses Server-Sent Events (SSE) to stream agent updates and answer chunks.
    """
    import json
    from fastapi.responses import StreamingResponse
    from app.agents.orchestrator import Orchestrator

    logger.info(
        f"[CHAT_STREAM] Starting stream for chat_id={chat_id}, user_id={user_id}"
    )
    logger.debug(
        f"[CHAT_STREAM] Request: query='{request.query[:50]}...', use_web={request.use_web}, doc_ids={request.document_ids}"
    )

    try:
        supabase = get_supabase_client()

        # Verify chat ownership
        chat_response = (
            supabase.table("chats")
            .select("*")
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not chat_response.data:
            logger.warning(
                f"[CHAT_STREAM] Chat not found: chat_id={chat_id}, user_id={user_id}"
            )
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = chat_response.data
        thread_id = chat.get("thread_id")

        logger.info(f"[CHAT_STREAM] Chat verified: thread_id={thread_id}")

        if not thread_id:
            thread_id = f"chat-{chat_id}"
            logger.info(
                f"[CHAT_STREAM] Generated new thread_id={thread_id} for chat_id={chat_id}"
            )
            supabase.table("chats").update({"thread_id": thread_id}).eq(
                "id", chat_id
            ).execute()

        async def event_generator():
            """Generate SSE events for the research stream."""
            try:
                logger.info(
                    f"[CHAT_STREAM] Starting orchestrator for thread_id={thread_id}"
                )
                orchestrator = Orchestrator(user_id)

                accumulated_answer = ""
                accumulated_thinking = ""

                # Stream research with chat context
                async for event in orchestrator.research_stream_with_context(
                    query=request.query,
                    chat_id=UUID(chat_id),
                    thread_id=thread_id,
                    use_web=request.use_web,
                    document_ids=request.document_ids,
                ):
                    event_type = event.get("type", "unknown")
                    logger.debug(
                        f"[CHAT_STREAM] Event: type={event_type}, node={event.get('node', 'N/A')}"
                    )

                    if event_type == "node_complete":
                        yield f"event: agent_status\ndata: {json.dumps({'node': event.get('node'), 'status': 'complete'})}\n\n"

                    elif event_type == "answer_chunk":
                        content = event.get("content", "")
                        accumulated_answer += content
                        yield f"event: answer_chunk\ndata: {json.dumps({'content': content})}\n\n"

                    elif event_type == "thought_chunk":
                        content = event.get("content", "")
                        accumulated_thinking += content
                        yield f"event: thought_chunk\ndata: {json.dumps({'content': content})}\n\n"

                    elif event_type == "sources":
                        logger.info(
                            f"[CHAT_STREAM] Sources received: {len(event.get('sources', []))} sources"
                        )
                        yield f"event: sources\ndata: {json.dumps({'sources': event.get('sources', [])})}\n\n"

                    elif event_type == "complete":
                        # Store message in database
                        message_id = str(UUID(event.get("session_id")))
                        logger.info(
                            f"[CHAT_STREAM] Research complete, storing message_id={message_id}"
                        )

                        # Use agent_timeline from event if available, otherwise empty
                        agent_timeline = event.get("agent_timeline", [])

                        # Fallback to DB if empty (legacy support)
                        if not agent_timeline:
                            try:
                                timeline_logs = (
                                    supabase.table("agent_logs")
                                    .select("*")
                                    .eq("session_id", event.get("session_id"))
                                    .order("created_at")
                                    .execute()
                                )
                                agent_timeline = [
                                    {
                                        "agent": log["agent_name"],
                                        "latency_ms": log["latency_ms"],
                                        "events": log["events"],
                                    }
                                    for log in timeline_logs.data
                                ]
                            except Exception as e:
                                logger.error(
                                    f"[CHAT_STREAM] Failed to fetch timeline logs: {e}"
                                )
                                agent_timeline = []

                        logger.info(
                            f"[CHAT_STREAM] Inserting message. Thinking len: {len(accumulated_thinking)}, Timeline len: {len(agent_timeline)}"
                        )

                        supabase.table("messages").insert(
                            sanitize_for_postgres(
                                {
                                    "id": message_id,
                                    "chat_id": chat_id,
                                    "session_id": event.get("session_id"),
                                    "query": request.query,
                                    "answer": accumulated_answer,
                                    "thinking": accumulated_thinking,
                                    "agent_timeline": agent_timeline,
                                    "role": "assistant",
                                    "sources": event.get("sources", []),
                                    "verification": event.get("verification"),
                                    "confidence": event.get("confidence"),
                                }
                            )
                        ).execute()

                        complete_data = {
                            "message_id": message_id,
                            "session_id": event.get("session_id"),
                            "confidence": event.get("confidence", "unknown"),
                            "total_latency_ms": event.get("total_latency_ms", 0),
                            "sources": event.get("sources", []),
                            "verification": event.get("verification"),
                        }
                        logger.info(
                            f"[CHAT_STREAM] Stream complete: message_id={message_id}, latency={event.get('total_latency_ms', 0)}ms"
                        )
                        yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"

            except Exception as e:
                logger.error(
                    f"[CHAT_STREAM] Error in event generator: {str(e)}", exc_info=True
                )
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[CHAT_STREAM] Error in stream setup for chat_id={chat_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {str(e)}")


# ============================================
# Memory Endpoints
# ============================================


@router.get("/{chat_id}/memory")
async def get_chat_memory(
    chat_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get agent memory context for a chat.

    Returns episodic memories (past agent executions) for all agents.
    Used by the Timeline panel to show what agents remember.
    """
    supabase = get_supabase_client()

    # Verify chat ownership
    chat_check = (
        supabase.table("chats")
        .select("id")
        .eq("id", chat_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chat_check.data:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get memory from Store
    memory_service = get_agent_memory_service()

    memory_context = await memory_service.build_memory_context(
        user_id=UUID(user_id),
        chat_id=UUID(chat_id),
    )

    return memory_context


@router.get("/{chat_id}/memory/{agent_name}")
async def get_agent_memory_for_chat(
    chat_id: str,
    agent_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get memory for a specific agent in a chat."""
    supabase = get_supabase_client()

    # Verify chat ownership
    chat_check = (
        supabase.table("chats")
        .select("id")
        .eq("id", chat_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not chat_check.data:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get memory from Store
    memory_service = get_agent_memory_service()

    memories = await memory_service.get_agent_memory(
        user_id=UUID(user_id),
        chat_id=UUID(chat_id),
        agent_name=agent_name,
    )

    return {"agent": agent_name, "memories": memories}
