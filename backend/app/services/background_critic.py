"""Background critic service for async verification."""

import asyncio
import logging
from uuid import UUID

from app.agents.critic import CriticAgent
from app.agents.base import AgentInput, AgentOutput
from app.core.database import get_supabase_client

logger = logging.getLogger(__name__)

# Keep strong references to background tasks so the GC cannot collect them
# before they finish.  Tasks remove themselves on completion.
_background_tasks: set[asyncio.Task] = set()


async def run_critic_background(
    session_id: str,
    chat_id: UUID,
    message_id: str,
    query: str,
    synthesis_result: dict,
    internal_sources: list[dict],
    web_sources: list[dict],
) -> None:
    """
    Run critic verification in the background and update the message.

    This function is designed to be fire-and-forget after synthesis completes.
    It updates the message with verification results when done.

    Args:
        session_id: Research session ID
        chat_id: Chat ID
        message_id: Message ID to update
        query: Original user query
        synthesis_result: Synthesis output with answer
        internal_sources: Retrieved document sources
        web_sources: Web search sources
    """
    logger.info(
        f"[BG_CRITIC] Starting background verification for message {message_id}"
    )

    critic = CriticAgent()

    context = {
        "synthesis_result": synthesis_result,
        "internal_sources": internal_sources,
        "web_sources": web_sources,
    }

    agent_input = AgentInput(
        query=query,
        context=context,
    )

    verification: dict = {}
    confidence = "unknown"

    try:
        output: AgentOutput = await critic.run(agent_input)
        verification = output.result
        confidence = verification.get("verification_status", "unknown")
        logger.info(f"[BG_CRITIC] Verification complete: {confidence}")
    except Exception as e:
        logger.warning(f"[BG_CRITIC] Critic failed: {e}")
        verification = {
            "verification_status": "unknown",
            "confidence_score": 0.5,
            "verified_claims": [],
            "unsupported_claims": [],
            "overall_assessment": "Verification failed due to API error",
        }
        confidence = "unknown"

    supabase = get_supabase_client()

    try:
        supabase.table("messages").update(
            {
                "verification": verification,
                "confidence": confidence,
            }
        ).eq("id", message_id).execute()
        logger.info(f"[BG_CRITIC] Updated message {message_id} with verification")
    except Exception as e:
        logger.error(f"[BG_CRITIC] Failed to update message: {e}")

    try:
        # Only patch the verification/confidence fields — do not overwrite the
        # sources, query, total_latency_ms, etc. that the orchestrator stored.
        # Fetch existing result first so we can merge rather than clobber.
        existing = (
            supabase.table("research_sessions")
            .select("result")
            .eq("id", session_id)
            .single()
            .execute()
        )
        existing_result: dict = {}
        if existing.data and isinstance(existing.data, dict):
            raw = existing.data.get("result")
            if isinstance(raw, dict):
                existing_result = raw

        merged_result = {
            **existing_result,
            "verification": verification,
            "confidence": confidence,
        }
        supabase.table("research_sessions").update({"result": merged_result}).eq(
            "id", session_id
        ).execute()
    except Exception as e:
        logger.error(f"[BG_CRITIC] Failed to update session: {e}")


def spawn_critic_task(
    session_id: str,
    chat_id: UUID,
    message_id: str,
    query: str,
    synthesis_result: dict,
    internal_sources: list[dict],
    web_sources: list[dict],
) -> asyncio.Task:
    """
    Spawn a background task for critic verification.

    Returns the task handle for potential cancellation.

    Args:
        session_id: Research session ID
        chat_id: Chat ID
        message_id: Message ID to update
        query: Original user query
        synthesis_result: Synthesis output with answer
        internal_sources: Retrieved document sources
        web_sources: Web search sources

    Returns:
        asyncio.Task handle
    """
    task = asyncio.create_task(
        run_critic_background(
            session_id=session_id,
            chat_id=chat_id,
            message_id=message_id,
            query=query,
            synthesis_result=synthesis_result,
            internal_sources=internal_sources,
            web_sources=web_sources,
        )
    )
    # Keep a strong reference so the GC cannot collect the task early.
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    logger.info(f"[BG_CRITIC] Spawned background critic task for message {message_id}")
    return task
