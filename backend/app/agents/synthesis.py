"""Synthesis Agent - Produces grounded answers from context."""

import re
import time
import json
import logging
from typing import AsyncGenerator

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client
from app.services.image_ingestion import get_image_ingestion_service

logger = logging.getLogger(__name__)


SYNTHESIS_SYSTEM_PROMPT = """You are a research synthesis agent. Your job is to produce accurate, well-cited answers based on provided context.

REASONING PROCESS (follow these steps internally before writing):
1. Identify the key aspects of the question
2. Scan each source for relevant information
3. Check for contradictions between sources
4. Determine confidence level based on source agreement and quality
5. Plan the answer structure

CITATION RULES (CRITICAL):
1. ONLY use information explicitly stated in the provided sources
2. Every factual claim MUST have an inline citation using [Source N] format
3. If sources conflict, acknowledge both perspectives with citations
4. If information is not in the context, explicitly state "I could not find information about X"
5. NEVER infer, assume, or extrapolate beyond what sources explicitly state
6. When uncertain, prefer to say "The sources suggest..." rather than stating as fact

ANSWER STRUCTURE:
1. Lead with the most direct answer to the question
2. Provide supporting details with citations
3. Include background/context when it aids understanding
4. Note any limitations, caveats, or gaps in the available information
5. For complex topics, use sections or bullet points for clarity

Output format:
{
    "answer": "Your synthesized answer with [Source 1] inline citations for every claim",
    "sources_used": [1, 2, 3],
    "confidence": "high|medium|low",
    "reasoning": "Brief explanation of how you synthesized the answer and any source conflicts",
    "sections": [
        {"title": "Section Title", "content": "Section content with [Source N] citations"}
    ]
}
"""


SYNTHESIS_STREAMING_PROMPT = """You are a research synthesis agent. Your job is to produce accurate, well-cited answers based on provided context.

REASONING PROCESS (think through these before writing):
1. What are the key aspects of the question?
2. What does each source say about these aspects?
3. Are there any contradictions between sources?
4. What is my confidence level based on source quality and agreement?

WHEN IMAGES ARE PROVIDED:
1. Analyze the visual content directly - describe what you see
2. Reference images using [Image N] format
3. Connect visual observations to any text sources
4. Note any details in images that answer the question

IMAGE GENERATION (ALREADY GENERATED):
A separate system handles image generation BEFORE you run. If an image was generated, it will be appended to your response automatically.
Your job is to acknowledge the image briefly (e.g., "Here is the generated image of X.") while still providing a comprehensive, research-style answer if requested.
Do NOT output any JSON, tool calls, or code to create the image.

CITATION RULES (CRITICAL):
1. ONLY use information explicitly stated in the provided sources
2. Every factual claim MUST have an inline citation using [Source N] format
3. Reference images with [Image N] format when describing visual content
4. If sources conflict, acknowledge both perspectives with their citations
5. If information is not available, explicitly state "I could not find information about X"
6. NEVER infer, assume, or extrapolate beyond what sources explicitly state

FORMATTING:
1. Use markdown formatting: headers (##), bullet points, bold for emphasis
2. Lead with the most direct answer to the question
3. Provide supporting details with citations
4. Note any limitations or gaps in the available information
5. For complex topics, use sections for clarity

MATH/SCIENTIFIC NOTATION (CRITICAL):
1. Use LaTeX for ALL mathematical expressions, chemical formulas, and scientific notation
2. ALWAYS use double dollar signs $$...$$ for ALL math (Streamdown does not support single $ to avoid currency conflicts)
3. Inline math: $$E = mc^2$$ or $$Mg^{2+}$$ (double dollars, inline with text)
4. Display math: put $$...$$ on its own line for block equations like $$\\sum_{i=1}^n x_i$$
5. Chemical formulas: $$H_2O$$, $$CO_2$$, $$Ca^{2+}$$, $$SO_4^{2-}$$
6. Subscripts: $$x_1$$, $$H_2O$$ | Superscripts: $$x^2$$, $$Fe^{3+}$$
7. Greek letters: $$\\alpha$$, $$\\beta$$, $$\\gamma$$, $$\\Delta$$
8. WRONG: $Mg^{2+}$ (single dollar) or (Mg²⁺) | CORRECT: $$Mg^{2+}$$

Write a well-formatted markdown response with inline citations. Do NOT wrap in JSON."""


CONCISE_QUERY_PATTERNS = (
    r"\bbrief\b",
    r"\bbriefly\b",
    r"\bshort answer\b",
    r"\bsummary\b",
    r"\bsummarize\b",
    r"\btl;?dr\b",
    r"\bconcise\b",
    r"\bone paragraph\b",
    r"\bfew sentences\b",
    r"\bquick answer\b",
)


class SynthesisAgent(BaseAgent):
    """Agent that synthesizes context into a grounded answer."""

    name = "synthesis"

    def __init__(self):
        self.gemini = get_gemini_client()
        self.image_service = get_image_ingestion_service()

    @staticmethod
    def _should_be_concise(query: str) -> bool:
        normalized = query.strip().lower()
        return any(re.search(pattern, normalized) for pattern in CONCISE_QUERY_PATTERNS)

    @classmethod
    def _build_detail_guidance(cls, query: str) -> str:
        if cls._should_be_concise(query):
            return (
                "The user requested a brief response. Keep it tight (around 4-6 sentences), "
                "focus on the key facts, and still include citations."
            )
        return (
            "Provide a research-style response with context, key points, and implications or "
            "limitations. Aim for multiple paragraphs or labeled sections while staying grounded "
            "in the sources."
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """Synthesize an answer from the provided context."""
        start_time = time.perf_counter()

        detail_guidance = self._build_detail_guidance(input.query)

        # Get context from previous agents
        internal_context = input.context.get("internal_sources", [])
        web_context = input.context.get("web_sources", [])

        # Build the context section
        context_parts = []
        source_map = {}
        source_num = 1

        # Add internal sources
        for source in internal_context:
            context_parts.append(
                f"[Source {source_num}] (Internal Document)\n{source.get('content', '')}"
            )
            source_map[source_num] = {
                "type": "internal",
                "chunk_id": source.get("chunk_id"),
                "document_id": source.get("document_id"),
            }
            source_num += 1

        # Add web sources
        for source in web_context:
            context_parts.append(
                f"[Source {source_num}] ({source.get('url', 'Web')})\n{source.get('content', '')}"
            )
            source_map[source_num] = {
                "type": "web",
                "url": source.get("url"),
                "title": source.get("title"),
            }
            source_num += 1

        # Add image sources (text descriptions for context)
        image_num = 1
        for image in input.images:
            context_parts.append(
                f"[Image {image_num}] (Image: {image.filename})\nDescription: {image.description}"
            )
            source_map[f"image_{image_num}"] = {
                "type": "image",
                "document_id": image.document_id,
                "filename": image.filename,
                "storage_path": image.storage_path,
            }
            image_num += 1

        context_text = "\n\n---\n\n".join(context_parts)

        # Build the prompt
        prompt = f"""Answer this research question based on the provided context:

Question: {input.query}

Response detail guidance: {detail_guidance}

Context:
{context_text}

Produce a well-cited answer in JSON format."""

        # Generate synthesis
        response = self.gemini.generate_json(
            prompt=prompt,
            system_instruction=SYNTHESIS_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=3072,
        )

        # Parse response with error handling
        try:
            result = self._parse_json_response(response)

            # Validate required fields exist
            if "answer" not in result:
                logger.warning(
                    f"[{self.name}] Missing 'answer' field in response, using default"
                )
                result["answer"] = (
                    "I encountered an issue generating a complete answer. Please try again."
                )

            if "sources_used" not in result:
                result["sources_used"] = []

            if "confidence" not in result:
                result["confidence"] = "low"

            if "sections" not in result:
                result["sections"] = []

        except json.JSONDecodeError as e:
            logger.error(
                f"[{self.name}] Failed to parse synthesis response: {e}\n"
                f"Response length: {len(response)}\n"
                f"Response preview: {response[:500]}"
            )

            # Return a safe default response that matches expected schema
            result = {
                "answer": (
                    "I apologize, but I encountered a technical issue while synthesizing the information "
                    "from the sources. This is likely due to the complexity or size of the content. "
                    "Please try rephrasing your question or breaking it into smaller parts."
                ),
                "sources_used": [],
                "confidence": "low",
                "sections": [],
                "error": "json_parse_error",
                "raw_response_preview": response[:500] if response else "No response",
            }

        result["source_map"] = source_map

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=result,
            metadata={
                "total_sources": len(source_map),
                "internal_count": len(internal_context),
                "web_count": len(web_context),
            },
            latency_ms=latency,
        )

    async def run_stream(self, input: AgentInput) -> AsyncGenerator[dict, None]:
        """
        Synthesize an answer with streaming output.

        Yields chunks of the answer as they're generated.
        Final yield is the complete AgentOutput.
        """
        start_time = time.perf_counter()

        detail_guidance = self._build_detail_guidance(input.query)

        # Get context from previous agents
        internal_context = input.context.get("internal_sources", [])
        web_context = input.context.get("web_sources", [])

        # Build the context section
        context_parts = []
        source_map = {}
        source_num = 1

        # Add internal sources
        for source in internal_context:
            context_parts.append(
                f"[Source {source_num}] (Internal Document)\n{source.get('content', '')}"
            )
            source_map[source_num] = {
                "type": "internal",
                "chunk_id": source.get("chunk_id"),
                "document_id": source.get("document_id"),
            }
            source_num += 1

        # Add web sources
        for source in web_context:
            context_parts.append(
                f"[Source {source_num}] ({source.get('url', 'Web')})\n{source.get('content', '')}"
            )
            source_map[source_num] = {
                "type": "web",
                "url": source.get("url"),
                "title": source.get("title"),
            }
            source_num += 1

        # Add image sources (text descriptions as context reference)
        image_num = 1
        image_bytes_list: list[dict] = []  # For multimodal API
        for image in input.images:
            context_parts.append(
                f"[Image {image_num}] (Image: {image.filename})\nDescription: {image.description}"
            )
            source_map[f"image_{image_num}"] = {
                "type": "image",
                "document_id": image.document_id,
                "filename": image.filename,
                "storage_path": image.storage_path,
            }
            # Load image bytes for multimodal API
            try:
                img_bytes = await self.image_service.get_image_bytes(image.storage_path)
                if img_bytes:
                    image_bytes_list.append(
                        {
                            "bytes": img_bytes,
                            "mime_type": image.mime_type,
                        }
                    )
                    logger.info(
                        f"[{self.name}] Loaded image {image_num}: {image.filename}"
                    )
            except Exception as e:
                logger.warning(
                    f"[{self.name}] Failed to load image {image.filename}: {e}"
                )
            image_num += 1

        context_text = "\n\n---\n\n".join(context_parts)
        has_images = len(image_bytes_list) > 0

        # Check for generated image from image_gen node
        generated_image_url = input.context.get("generated_image_url")
        if generated_image_url:
            logger.info(
                f"[{self.name}] Including generated image in answer: {generated_image_url}"
            )

        # Check if this is a refinement pass
        is_refinement = input.context.get("is_refinement", False)

        # Build the prompt for streaming (markdown output, not JSON)
        if is_refinement:
            # Refinement prompt includes previous answer and critic feedback
            previous_answer = input.context.get("previous_answer", "")
            critic_feedback = input.context.get("critic_feedback", "")
            verification_status = input.context.get("verification_status", "unknown")

            logger.info(
                f"[{self.name}] Refinement mode: status={verification_status}, "
                f"feedback_len={len(critic_feedback)}"
            )

            prompt = f"""You are refining a research answer based on critic feedback.

Question: {input.query}

## Previous Answer (needs improvement):
{previous_answer}

## Critic Feedback (verification status: {verification_status}):
{critic_feedback}

## Available Sources:
{context_text}

## Your Task:
1. Review the critic's feedback carefully
2. Fix ALL unsupported claims by either:
   - Adding proper citations from the sources
   - Removing claims not supported by sources
   - Rewording to accurately reflect what sources say
3. Address ALL missing citations
4. Fill any coverage gaps if the sources support it
5. Resolve conflicting information by acknowledging different perspectives

Response detail guidance: {detail_guidance}

Write an IMPROVED answer that addresses ALL the critic's concerns. 
Use inline [Source N] citations for every factual claim.
DO NOT repeat the same unsupported claims."""
        else:
            # Build image generation context for the prompt
            image_gen_note = ""
            if generated_image_url:
                image_gen_note = (
                    "\n\n*** IMAGE ALREADY GENERATED ***\n"
                    "An image has ALREADY been generated for this request by an external system. "
                    "It will be appended to your response automatically.\n"
                    "You MUST:\n"
                    "- Acknowledge the generated image briefly (e.g., 'Here is the visualization of X you requested.')\n"
                    "- Do NOT output any JSON, tool calls, or code to generate the image.\n"
                    "- You MAY still provide a research-style answer with citations if the query requires it, "
                    "integrating the acknowledgment naturally.\n"
                )

            prompt = f"""Answer this research question based on the provided context:

Question: {input.query}

Response detail guidance: {detail_guidance}
{image_gen_note}
Context:
{context_text}

Write a well-formatted markdown answer with inline [Source N] citations."""

        # Stream the answer (multimodal if images present)
        full_answer = ""
        full_thoughts = ""
        try:
            if has_images:
                # Use multimodal streaming with images
                logger.info(
                    f"[{self.name}] Using multimodal stream with {len(image_bytes_list)} images"
                )
                stream = self.gemini.generate_stream_with_images(
                    prompt=prompt,
                    images=image_bytes_list,
                    system_instruction=SYNTHESIS_STREAMING_PROMPT,
                    temperature=1.0,  # Gemini 3 default
                    max_tokens=3072,
                    include_thoughts=True,
                )
            else:
                # Use text-only streaming
                stream = self.gemini.generate_stream(
                    prompt=prompt,
                    system_instruction=SYNTHESIS_STREAMING_PROMPT,
                    temperature=0.5,
                    max_tokens=3072,
                    include_thoughts=True,
                )

            async for chunk in stream:
                chunk_type = chunk.get("type", "text")
                chunk_content = chunk.get("content", "")

                # Ensure chunk_content is a string
                if not isinstance(chunk_content, str):
                    logger.warning(
                        f"[{self.name}] Unexpected chunk content type: "
                        f"{type(chunk_content)}, skipping"
                    )
                    continue

                if chunk_type == "thought":
                    full_thoughts += chunk_content
                    yield {"type": "thought_chunk", "content": chunk_content}
                elif chunk_type == "text":
                    full_answer += chunk_content
                    yield {"type": "answer_chunk", "content": chunk_content}
        except Exception as e:
            logger.error(f"[{self.name}] Streaming error: {e}", exc_info=True)
            full_answer = (
                "I apologize, but I encountered an issue generating a response. "
                "Please try again."
            )
            yield {"type": "answer_chunk", "content": full_answer}

        latency = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            f"[{self.name}] Streaming complete: answer={len(full_answer)} chars, "
            f"thoughts={len(full_thoughts)} chars, latency={latency}ms"
        )

        # Append generated image to answer if available and stream it to client
        if generated_image_url:
            image_markdown = f"\n\n![Generated Image]({generated_image_url})"
            full_answer += image_markdown
            yield {"type": "answer_chunk", "content": image_markdown}
            logger.info(f"[{self.name}] Appended generated image to answer")

        # Extract sources used from the answer (look for [Source N] patterns)

        sources_used = list(
            set(int(m) for m in re.findall(r"\[Source (\d+)\]", full_answer))
        )

        # Build final result
        result = {
            "answer": full_answer,
            "sources_used": sources_used,
            "confidence": "medium",  # Default for streaming
            "sections": [],
            "source_map": source_map,
        }

        # Yield final output
        logger.info(f"[{self.name}] Yielding complete event")
        yield {
            "type": "complete",
            "output": AgentOutput(
                agent_name=self.name,
                result=result,
                metadata={
                    "total_sources": len(source_map),
                    "internal_count": len(internal_context),
                    "web_count": len(web_context),
                    "streaming": True,
                },
                latency_ms=latency,
            ),
        }
