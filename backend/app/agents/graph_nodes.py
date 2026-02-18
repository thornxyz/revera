"""LangGraph node functions that wrap existing agents.

Each node accepts (state, config) and dispatches custom events via
adispatch_custom_event so the orchestrator can stream them as SSE.
"""

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from app.agents.base import AgentInput, AgentOutput, ImageContext
from app.agents.planner import PlannerAgent
from app.agents.retrieval import RetrievalAgent
from app.agents.web_search import WebSearchAgent
from app.agents.synthesis import SynthesisAgent
from app.agents.critic import CriticAgent
from app.agents.graph_state import ResearchState
from app.services.agent_memory import get_agent_memory_service
from app.services.image_ingestion import get_image_ingestion_service
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


def _get_plan_constraints(state: ResearchState) -> dict[str, Any]:
    """Safely extract constraints from execution plan in state."""
    plan = state.get("execution_plan")
    if plan is not None:
        return plan.constraints
    return {}


def _get_memory_prompt(state: ResearchState, agent_name: str) -> str:
    """Format memory context for a specific agent from state."""
    memory_context = state.get("memory_context") or {}
    memories = memory_context.get(agent_name, [])
    if not memories:
        return ""
    memory_service = get_agent_memory_service()
    return memory_service.format_memory_for_prompt(agent_name, memories)


# Node: Planning
async def planning_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Analyze the query and create an execution plan.

    Returns updates to state including execution_plan and timeline entry.
    """
    logger.info(f"[GRAPH] Planning node for query: {state['query'][:50]}...")

    planner = PlannerAgent()

    memory_prompt = _get_memory_prompt(state, "planner")

    agent_input = AgentInput(
        query=state["query"],
        constraints={
            "use_web": state.get("use_web", True),
            "memory_prompt": memory_prompt,
        },
    )

    output = await planner.run(agent_input)

    return {
        "execution_plan": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Retrieval
async def retrieval_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Execute hybrid RAG search on internal documents.

    Dispatches a 'sources' custom event after search completes.
    Returns updates to state including internal_sources and timeline entry.
    """
    logger.info("[GRAPH] Retrieval node executing...")

    retrieval = RetrievalAgent(state["user_id"])

    memory_prompt = _get_memory_prompt(state, "retrieval")

    constraints = _get_plan_constraints(state)

    # Extract step description from plan for focused retrieval
    step_description = None
    plan = state.get("execution_plan")
    if plan:
        for step in plan.steps:
            if step.tool == "rag":
                step_description = step.description
                break
        if step_description:
            logger.info(f"[GRAPH] Using step description: {step_description[:50]}...")

    context: dict[str, Any] = {
        "document_ids": state.get("document_ids"),
        "step_description": step_description,
    }
    if memory_prompt:
        context["memory_prompt"] = memory_prompt

    agent_input = AgentInput(
        query=state["query"],
        context=context,
        constraints=constraints,
    )

    output = await retrieval.run(agent_input)

    logger.info(f"[GRAPH] Retrieved {len(output.result)} sources")

    # Dispatch sources event for real-time streaming
    await adispatch_custom_event(
        "sources",
        {"sources": output.result},
        config=config,
    )

    return {
        "internal_sources": output.result,
        "agent_timeline": [output.to_dict()],
    }


# Node: Web Search
async def web_search_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Execute web search using Tavily API.

    Handles its own skip logic: returns empty results if web search
    is disabled or not needed by the plan. This enables parallel
    fan-out from planning (retrieval + web_search run concurrently).

    Dispatches a 'sources' custom event after search completes.
    Returns updates to state including web_sources and timeline entry.
    """
    # Check if web search should run
    if not state.get("use_web", True):
        logger.info("[GRAPH] Web search disabled by user, skipping")
        return {"web_sources": [], "agent_timeline": []}

    plan = state.get("execution_plan")
    if plan and not any(step.tool == "web" for step in plan.steps):
        logger.info("[GRAPH] Plan does not include web search, skipping")
        return {"web_sources": [], "agent_timeline": []}

    logger.info("[GRAPH] Web search node executing...")

    web_search = WebSearchAgent()

    # Get constraints from execution plan
    constraints = {}
    step_description = None
    if plan:
        constraints = plan.constraints
        # Extract step description for focused search
        for step in plan.steps:
            if step.tool == "web":
                step_description = step.description
                break
        if step_description:
            logger.info(
                f"[GRAPH] Using web step description: {step_description[:50]}..."
            )

    agent_input = AgentInput(
        query=state["query"],
        context={"step_description": step_description},
        constraints=constraints,
    )

    output = await web_search.run(agent_input)

    logger.info(f"[GRAPH] Found {len(output.result)} web sources")

    # Extract Tavily's quick answer if available
    tavily_answer = output.metadata.get("tavily_answer")
    if tavily_answer:
        logger.info(
            f"[GRAPH] Tavily quick answer available ({len(tavily_answer)} chars)"
        )
        # Dispatch quick answer for immediate display before synthesis
        await adispatch_custom_event(
            "quick_answer",
            {"answer": tavily_answer, "source": "tavily"},
            config=config,
        )

    # Dispatch sources event for real-time streaming
    if output.result:
        await adispatch_custom_event(
            "sources",
            {"sources": output.result},
            config=config,
        )

    return {
        "web_sources": output.result,
        "tavily_answer": tavily_answer,
        "agent_timeline": [output.to_dict()],
    }


# Node: Image Generation
async def image_gen_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Generate an image from the user query using Gemini.

    Handles its own skip logic: returns empty if image_gen
    is not in the plan. This enables parallel fan-out from planning.

    Returns updates to state including generated_image_url and timeline entry.
    """
    plan = state.get("execution_plan")
    if not plan or not any(step.tool == "image_gen" for step in plan.steps):
        logger.info("[GRAPH] Plan does not include image_gen, skipping")
        return {
            "agent_timeline": [],
        }

    logger.info("[GRAPH] Image generation node executing...")

    gemini = get_gemini_client()
    image_ingestion = get_image_ingestion_service()
    start_time = time.perf_counter()

    try:
        query = state["query"]
        user_id = state["user_id"]
        chat_id = state.get("chat_id")

        # Use the planner's step description as a refined image prompt
        image_prompt = query
        if plan:
            for step in plan.steps:
                if step.tool == "image_gen" and step.description:
                    image_prompt = step.description
                    break

        logger.info(f"[GRAPH] Image generation prompt: {image_prompt[:80]}...")
        image_bytes_list = await gemini.generate_image(image_prompt)

        if not image_bytes_list:
            logger.warning("[GRAPH] No images were generated by the model")
            latency = int((time.perf_counter() - start_time) * 1000)
            return {
                "generated_image_url": None,
                "generated_image_storage_path": None,
                "agent_timeline": [
                    {
                        "agent_name": "image_gen",
                        "result": {"status": "no_images_returned"},
                        "latency_ms": latency,
                    }
                ],
            }

        image_bytes = image_bytes_list[0]

        storage_path = await image_ingestion.save_generated_image(
            image_bytes=image_bytes,
            user_id=UUID(user_id),
            prompt=image_prompt,
            chat_id=UUID(chat_id) if chat_id else None,
        )

        public_url = image_ingestion.get_public_image_url(storage_path)
        if not public_url:
            raise ValueError("Failed to create public image URL")

        latency = int((time.perf_counter() - start_time) * 1000)
        logger.info(f"[GRAPH] Image generated successfully: {public_url} ({latency}ms)")

        return {
            "generated_image_url": public_url,
            "generated_image_storage_path": storage_path,
            "agent_timeline": [
                {
                    "agent_name": "image_gen",
                    "result": {"url": public_url, "storage_path": storage_path},
                    "latency_ms": latency,
                }
            ],
        }

    except Exception as e:
        latency = int((time.perf_counter() - start_time) * 1000)
        logger.error(f"[GRAPH] Image generation failed ({latency}ms): {e}")
        return {
            "generated_image_url": None,
            "generated_image_storage_path": None,
            "agent_timeline": [
                {
                    "agent_name": "image_gen",
                    "result": {"error": str(e)},
                    "latency_ms": latency,
                }
            ],
        }


# Node: Synthesis
async def synthesis_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Combine all retrieved context into a grounded answer.

    Streams answer and thought chunks via adispatch_custom_event so the
    orchestrator can forward them as SSE events in real time.

    If this is a refinement pass (critic feedback exists), the previous answer
    and critic feedback are included so synthesis can improve the answer.

    Returns updates to state including synthesis_result and timeline entry.
    """
    is_refinement = state.get("verification") is not None
    logger.info(f"[GRAPH] Synthesis node executing... (refinement={is_refinement})")

    synthesis = SynthesisAgent()

    memory_prompt = _get_memory_prompt(state, "synthesis")

    constraints = _get_plan_constraints(state)

    context: dict[str, Any] = {
        "internal_sources": state.get("internal_sources", []),
        "web_sources": state.get("web_sources", []),
        "generated_image_url": state.get("generated_image_url"),
    }
    if memory_prompt:
        context["memory_prompt"] = memory_prompt

    # If this is a refinement pass, include critic feedback for improvement
    if is_refinement:
        verification = state.get("verification", {})
        previous_answer = state.get("synthesis_result", {}).get("answer", "")

        # Build critic feedback for the prompt
        critic_feedback_parts = []

        # Add overall assessment
        if verification.get("overall_assessment"):
            critic_feedback_parts.append(
                f"Overall Assessment: {verification['overall_assessment']}"
            )

        # Add unsupported claims
        unsupported = verification.get("unsupported_claims", [])
        if unsupported:
            claims_text = "\n".join(
                f"- {claim.get('claim', '')} (Reason: {claim.get('reason', 'unknown')}, "
                f"Severity: {claim.get('severity', 'unknown')})"
                for claim in unsupported
            )
            critic_feedback_parts.append(f"Unsupported Claims:\n{claims_text}")

        # Add missing citations
        missing = verification.get("missing_citations", [])
        if missing:
            missing_text = "\n".join(
                f'- "{cite.get("statement", "")}" - Suggestion: {cite.get("suggestion", "add citation")}'
                for cite in missing
            )
            critic_feedback_parts.append(f"Missing Citations:\n{missing_text}")

        # Add coverage gaps
        gaps = verification.get("coverage_gaps", [])
        if gaps:
            gaps_text = "\n".join(f"- {gap}" for gap in gaps)
            critic_feedback_parts.append(f"Coverage Gaps:\n{gaps_text}")

        # Add conflicting information
        conflicts = verification.get("conflicting_information", [])
        if conflicts:
            conflicts_text = "\n".join(
                f"- {c.get('topic', 'unknown')}: {c.get('description', '')}"
                for c in conflicts
            )
            critic_feedback_parts.append(f"Conflicting Information:\n{conflicts_text}")

        context["is_refinement"] = True
        context["previous_answer"] = previous_answer
        context["critic_feedback"] = "\n\n".join(critic_feedback_parts)
        context["verification_status"] = verification.get(
            "verification_status", "unknown"
        )

        logger.info(
            f"[GRAPH] Refinement pass with {len(unsupported)} unsupported claims, "
            f"{len(missing)} missing citations, {len(gaps)} coverage gaps"
        )

    # Convert image_contexts from state to ImageContext objects
    image_contexts = state.get("image_contexts", [])
    images = [
        ImageContext(
            document_id=img.get("document_id", ""),
            filename=img.get("filename", "image"),
            storage_path=img.get("storage_path", ""),
            description=img.get("description", ""),
            mime_type=img.get("mime_type", "image/jpeg"),
        )
        for img in image_contexts
    ]
    if images:
        logger.info(f"[GRAPH] Passing {len(images)} images to synthesis")

    agent_input = AgentInput(
        query=state["query"],
        context=context,
        constraints=constraints,
        images=images,
    )

    # Stream synthesis — dispatch chunks as custom events
    synthesis_output: AgentOutput | None = None

    async for chunk in synthesis.run_stream(agent_input):
        chunk_type = chunk.get("type")

        if chunk_type == "thought_chunk":
            await adispatch_custom_event(
                "thought_chunk",
                {"content": chunk.get("content", "")},
                config=config,
            )
        elif chunk_type == "answer_chunk":
            await adispatch_custom_event(
                "answer_chunk",
                {"content": chunk.get("content", "")},
                config=config,
            )
        elif chunk_type == "complete":
            output = chunk.get("output")
            if isinstance(output, AgentOutput):
                synthesis_output = output

    if synthesis_output:
        logger.info(
            f"[GRAPH] Synthesis complete with confidence: "
            f"{synthesis_output.result.get('confidence', 'unknown')}"
        )
        return {
            "synthesis_result": synthesis_output.result,
            "agent_timeline": [synthesis_output.to_dict()],
        }

    logger.warning("[GRAPH] Synthesis completed without output")
    return {
        "synthesis_result": {},
        "agent_timeline": [],
    }


# Node: Critic/Verification
async def critic_node(state: ResearchState, config: RunnableConfig) -> dict:
    """
    Verify the synthesized answer against sources.

    Runs inline (not in background) so the feedback loop works.
    Returns updates to state including verification, needs_refinement flag,
    and timeline entry.
    """
    logger.info("[GRAPH] Critic node executing...")

    critic = CriticAgent()

    # Get memory context for consistency with past verifications
    memory_prompt = _get_memory_prompt(state, "critic")

    context = {
        "synthesis_result": state.get("synthesis_result"),
        "internal_sources": state.get("internal_sources", []),
        "web_sources": state.get("web_sources", []),
    }
    if memory_prompt:
        context["memory_prompt"] = memory_prompt

    agent_input = AgentInput(
        query=state["query"],
        context=context,
    )

    output: AgentOutput | None = None
    try:
        output = await critic.run(agent_input)
        verification = output.result
    except Exception as e:
        logger.warning(f"[GRAPH] Critic failed: {e}, using default verification")
        verification = {
            "verification_status": "unknown",
            "confidence_score": 0.5,
            "verified_claims": [],
            "unsupported_claims": [],
            "conflicting_information": [],
            "source_quality": {
                "internal_sources": {"count": 0, "reliability": "unknown"},
                "web_sources": {
                    "count": 0,
                    "reliability": "unknown",
                    "recency": "unknown",
                },
            },
            "missing_citations": [],
            "coverage_gaps": [],
            "overall_assessment": "Verification failed due to API error",
        }

    # Determine if we need refinement
    current_iteration = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 2)

    # Check confidence and verification status
    confidence = verification.get("verification_status", "unknown")
    needs_refinement = False

    if current_iteration < max_iterations:
        # If confidence is low or verification failed, trigger refinement
        if confidence in ["low", "failed", "unverified"]:
            needs_refinement = True
            logger.info(f"[GRAPH] Low confidence ({confidence}), triggering refinement")

    logger.info(
        f"[GRAPH] Verification complete: {confidence}, refinement needed: {needs_refinement}"
    )

    return {
        "verification": verification,
        "needs_refinement": needs_refinement,
        "iteration_count": current_iteration + 1,
        "agent_timeline": [output.to_dict()] if output is not None else [],
    }


# Conditional edge: Should we refine the answer?
def should_refine(state: ResearchState) -> str:
    """
    Decide whether to refine the answer or finish.

    Returns "synthesis" to refine, or "end" to finish.
    """
    if state.get("needs_refinement", False):
        logger.info("[GRAPH] Refinement needed, looping back to synthesis")
        return "synthesis"

    logger.info("[GRAPH] Answer verified, finishing")
    return "end"
