"""Chats API routes for multi-turn conversations."""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.core.auth import get_current_user_id
from app.core.database import get_supabase_client
from app.core.exceptions import ReveraError
from app.core.utils import sanitize_for_postgres
from app.core.validation import validated_uuid
from app.models.schemas import Chat, ChatCreate, ChatWithPreview, Message
from app.services.agent_memory import get_agent_memory_service

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 5000

# Maximum concurrent SSE streams allowed per user.
MAX_STREAMS_PER_USER = 3

# Per-user semaphores (lazily created, keyed by user_id).
_user_stream_semaphores: dict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(MAX_STREAMS_PER_USER)
)

router = APIRouter()


# ============================================
# Request/Response Models
# ============================================


class ChatQueryRequest(BaseModel):
    """Request body for sending a query in a chat."""

    query: str
    use_web: bool = True
    document_ids: list[str] | None = None

    @field_validator("query")
    @classmethod
    def validate_query_length(cls, v: str) -> str:
        """Reject excessively long prompts early."""
        if len(v) > MAX_QUERY_LENGTH:
            raise ValueError(f"Query must be at most {MAX_QUERY_LENGTH} characters")
        return v


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

    Uses optimized PostgreSQL function for single-query performance.
    """
    logger.info(f"[CHATS] Listing chats for user_id={user_id}")
    supabase = get_supabase_client()

    try:
        # Call optimized PostgreSQL function for single-query fetch
        response = supabase.rpc(
            "get_chats_with_preview", {"p_user_id": user_id}
        ).execute()

        if not response.data or not isinstance(response.data, list):
            logger.info(f"[CHATS] No chats found for user_id={user_id}")
            return []

        logger.info(
            f"[CHATS] Successfully retrieved {len(response.data)} chats with previews (optimized query)"
        )

        # Map database response to Pydantic model
        result = []
        for chat in response.data:
            if isinstance(chat, dict):
                result.append(
                    ChatWithPreview(
                        id=UUID(str(chat["id"])),
                        user_id=UUID(str(chat["user_id"])),
                        title=str(chat.get("title")) if chat.get("title") else None,
                        thread_id=(
                            str(chat.get("thread_id"))
                            if chat.get("thread_id")
                            else None
                        ),
                        created_at=datetime.fromisoformat(
                            str(chat["created_at"]).replace("Z", "+00:00")
                        ),
                        updated_at=datetime.fromisoformat(
                            str(chat["updated_at"]).replace("Z", "+00:00")
                        ),
                        last_message_preview=(
                            str(chat.get("last_message_preview"))
                            if chat.get("last_message_preview")
                            else None
                        ),
                        message_count=int(str(chat.get("message_count", 0))),
                    )
                )

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

        if (
            not response.data
            or not isinstance(response.data, list)
            or len(response.data) == 0
        ):
            logger.error("[CHATS] Failed to create chat: No data returned from insert")
            raise HTTPException(status_code=500, detail="Failed to create chat")

        created_chat = response.data[0]
        if not isinstance(created_chat, dict):
            logger.error("[CHATS] Failed to create chat: Invalid response format")
            raise HTTPException(status_code=500, detail="Failed to create chat")

        logger.info(f"[CHATS] Successfully created chat_id={created_chat['id']}")

        return Chat(
            id=UUID(str(created_chat["id"])),
            user_id=UUID(str(created_chat["user_id"])),
            title=str(created_chat.get("title")) if created_chat.get("title") else None,
            thread_id=(
                str(created_chat.get("thread_id"))
                if created_chat.get("thread_id")
                else None
            ),
            created_at=datetime.fromisoformat(
                str(created_chat["created_at"]).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                str(created_chat["updated_at"]).replace("Z", "+00:00")
            ),
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
    chat_id = validated_uuid(chat_id, "chat_id")

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

        if not response.data or not isinstance(response.data, dict):
            logger.warning(
                f"[CHATS] Chat not found: chat_id={chat_id}, user_id={user_id}"
            )
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = response.data
        logger.info(
            f"[CHATS] Successfully retrieved chat_id={chat_id}, title={chat.get('title') if isinstance(chat, dict) else None}"
        )

        return Chat(
            id=UUID(str(chat["id"])),
            user_id=UUID(str(chat["user_id"])),
            title=str(chat.get("title")) if chat.get("title") else None,
            thread_id=str(chat.get("thread_id")) if chat.get("thread_id") else None,
            created_at=datetime.fromisoformat(
                str(chat["created_at"]).replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                str(chat["updated_at"]).replace("Z", "+00:00")
            ),
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
    chat_id = validated_uuid(chat_id, "chat_id")
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

    if (
        not response.data
        or not isinstance(response.data, list)
        or len(response.data) == 0
    ):
        raise HTTPException(status_code=500, detail="Failed to update chat")

    updated = response.data[0]
    if not isinstance(updated, dict):
        raise HTTPException(status_code=500, detail="Failed to update chat")

    return Chat(
        id=UUID(str(updated["id"])),
        user_id=UUID(str(updated["user_id"])),
        title=str(updated.get("title")) if updated.get("title") else None,
        thread_id=str(updated.get("thread_id")) if updated.get("thread_id") else None,
        created_at=datetime.fromisoformat(
            str(updated["created_at"]).replace("Z", "+00:00")
        ),
        updated_at=datetime.fromisoformat(
            str(updated["updated_at"]).replace("Z", "+00:00")
        ),
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

    chat_id = validated_uuid(chat_id, "chat_id")

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
    chat_id = validated_uuid(chat_id, "chat_id")
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

    if not messages_response.data or not isinstance(messages_response.data, list):
        return []

    messages = []
    for msg in messages_response.data:
        if isinstance(msg, dict):
            # Convert sources to list[dict] if it's a valid JSON
            sources_val = msg.get("sources", [])
            sources_list: list[dict] = []
            if isinstance(sources_val, list):
                sources_list = [s for s in sources_val if isinstance(s, dict)]

            # Convert verification to dict if present
            verification_val = msg.get("verification")
            verification_dict = (
                verification_val if isinstance(verification_val, dict) else None
            )

            # Convert agent_timeline to list[dict] if present
            timeline_val = msg.get("agent_timeline")
            timeline_list: list[dict] | None = None
            if isinstance(timeline_val, list):
                timeline_list = [t for t in timeline_val if isinstance(t, dict)]

            messages.append(
                Message(
                    id=UUID(str(msg["id"])),
                    chat_id=UUID(str(msg["chat_id"])),
                    session_id=(
                        UUID(str(msg.get("session_id")))
                        if msg.get("session_id")
                        else None
                    ),
                    query=str(msg["query"]),
                    answer=str(msg.get("answer")) if msg.get("answer") else None,
                    role=str(msg["role"]),
                    sources=sources_list,
                    verification=verification_dict,
                    confidence=(
                        str(msg.get("confidence")) if msg.get("confidence") else None
                    ),
                    thinking=str(msg.get("thinking")) if msg.get("thinking") else None,
                    agent_timeline=timeline_list,
                    created_at=datetime.fromisoformat(
                        str(msg["created_at"]).replace("Z", "+00:00")
                    ),
                )
            )

    return messages


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

    chat_id = validated_uuid(chat_id, "chat_id")
    message_id = validated_uuid(message_id, "message_id")
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

    if not message_response.data or not isinstance(message_response.data, dict):
        raise HTTPException(status_code=404, detail="Message not found")

    message = message_response.data
    confidence = str(message.get("confidence", "unknown"))

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
    from fastapi.responses import StreamingResponse
    from app.agents.orchestrator import Orchestrator

    chat_id = validated_uuid(chat_id, "chat_id")
    logger.info(
        f"[CHAT_STREAM] Starting stream for chat_id={chat_id}, user_id={user_id}"
    )
    logger.debug(
        f"[CHAT_STREAM] Request: query='{request.query[:50]}...', use_web={request.use_web}, doc_ids={request.document_ids}"
    )

    try:
        supabase = get_supabase_client()

        chat_response = (
            supabase.table("chats")
            .select("id, thread_id, user_id")
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not chat_response.data or not isinstance(chat_response.data, dict):
            logger.warning(
                f"[CHAT_STREAM] Chat not found: chat_id={chat_id}, user_id={user_id}"
            )
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = chat_response.data
        thread_id = str(chat.get("thread_id")) if chat.get("thread_id") else None

        if not thread_id:
            thread_id = f"chat-{chat_id}"
            logger.info(
                f"[CHAT_STREAM] Generated new thread_id={thread_id} for chat_id={chat_id}"
            )
            supabase.table("chats").update({"thread_id": thread_id}).eq(
                "id", chat_id
            ).execute()

        logger.info(f"[CHAT_STREAM] Chat verified: thread_id={thread_id}")

        async def event_generator():
            """Generate SSE events for the research stream."""
            sem = _user_stream_semaphores[user_id]
            # Non-blocking acquire to check capacity.
            # timeout must be > 0 so the event loop gets at least one tick
            # to run the acquire coroutine (timeout=0 cancels before it runs).
            try:
                await asyncio.wait_for(sem.acquire(), timeout=0.01)
            except asyncio.TimeoutError:
                logger.warning(
                    f"[CHAT_STREAM] Too many concurrent streams for user_id={user_id}"
                )
                yield (
                    "event: error\ndata: "
                    + json.dumps(
                        {
                            "code": "TOO_MANY_STREAMS",
                            "message": "You have too many active streams. Please wait for one to finish.",
                            "recoverable": True,
                        }
                    )
                    + "\n\n"
                )
                return

            # Semaphore was acquired above — release it when the stream ends.
            try:
                try:
                    logger.info(
                        f"[CHAT_STREAM] Starting orchestrator for thread_id={thread_id}"
                    )
                    orchestrator = Orchestrator(user_id)

                    accumulated_answer = ""
                    accumulated_thinking = ""
                    message_id_from_orch = None

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

                        if event_type == "message_id":
                            message_id_from_orch = event.get("message_id")
                            yield f"event: message_id\ndata: {json.dumps({'message_id': message_id_from_orch})}\n\n"

                        elif event_type in ("node_started", "node_complete"):
                            yield f"event: agent_status\ndata: {json.dumps({'node': event.get('node'), 'status': event.get('status', 'complete')})}\n\n"

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

                        elif event_type == "title_updated":
                            yield f"event: title_updated\ndata: {json.dumps({'title': event.get('title'), 'chat_id': event.get('chat_id')})}\n\n"

                        elif event_type == "verification_pending":
                            yield f"event: verification_pending\ndata: {json.dumps({'session_id': event.get('session_id')})}\n\n"

                        elif event_type == "error":
                            yield f"event: error\ndata: {json.dumps({'message': event.get('message', 'Unknown error')})}\n\n"

                        elif event_type == "complete":
                            # Use message_id from early event, or fall back to session_id
                            message_id = message_id_from_orch or str(
                                UUID(event.get("session_id"))
                            )
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
                                    if isinstance(timeline_logs.data, list):
                                        for log in timeline_logs.data:
                                            if isinstance(log, dict):
                                                agent_timeline.append(
                                                    {
                                                        "agent": log.get("agent_name"),
                                                        "latency_ms": log.get(
                                                            "latency_ms"
                                                        ),
                                                        "events": log.get("events"),
                                                    }
                                                )
                                except Exception as e:
                                    logger.error(
                                        f"[CHAT_STREAM] Failed to fetch timeline logs: {e}"
                                    )
                                    agent_timeline = []

                            # Prefer definitive answer from orchestrator over accumulated chunks
                            final_answer = event.get("answer", accumulated_answer)

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
                                        "answer": final_answer,
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
                        f"[CHAT_STREAM] Error in event generator: {str(e)}",
                        exc_info=True,
                    )
                    # Emit structured error — never leak raw exception messages to the client
                    if isinstance(e, ReveraError):
                        error_payload = {
                            "code": e.error_code,
                            "message": e.message,
                            "recoverable": e.recoverable,
                        }
                    else:
                        error_payload = {
                            "code": "INTERNAL_ERROR",
                            "message": "An unexpected error occurred. Please try again.",
                            "recoverable": True,
                        }
                    yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

            finally:
                sem.release()

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
    chat_id = validated_uuid(chat_id, "chat_id")
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
