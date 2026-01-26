"""Synthesis Agent - Produces grounded answers from context."""

import re
import time
import json
import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


SYNTHESIS_SYSTEM_PROMPT = """You are a research synthesis agent. Your job is to produce accurate, well-cited answers based on provided context.

Rules:
1. ONLY use information from the provided context
2. Cite sources inline using [Source N] format where N is the source number
3. If information is not in the context, say "I could not find information about X"
4. Default to a moderately detailed, research-style response with multiple paragraphs
5. Include background/context, key points, and implications or limitations when possible
6. Use labeled sections or clear paragraph breaks when it helps readability
7. If the question explicitly asks for a brief/summary response, keep it concise
8. Never make up information

Output format:
{
    "answer": "Your synthesized answer with [Source 1] inline citations",
    "sources_used": [1, 2, 3],
    "confidence": "high|medium|low",
    "sections": [
        {"title": "Section Title", "content": "Section content with [Source N] citations"}
    ]
}
"""


SYNTHESIS_STREAMING_PROMPT = """You are a research synthesis agent. Your job is to produce accurate, well-cited answers based on provided context.

Rules:
1. ONLY use information from the provided context
2. Cite sources inline using [Source N] format where N is the source number
3. If information is not in the context, say "I could not find information about X"
4. Default to a moderately detailed, research-style response with multiple paragraphs
5. Include background/context, key points, and implications or limitations when possible
6. Use markdown formatting: headers (##), bullet points, bold for emphasis, code blocks when appropriate
7. If the question explicitly asks for a brief/summary response, keep it concise
8. Never make up information

Write a well-formatted markdown response with inline citations. Do NOT wrap in JSON.
"""


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

    @staticmethod
    def _should_be_concise(query: str) -> bool:
        normalized = query.strip().lower()
        return any(re.search(pattern, normalized) for pattern in CONCISE_QUERY_PATTERNS)

    async def run(self, input: AgentInput) -> AgentOutput:
        """Synthesize an answer from the provided context."""
        start_time = time.perf_counter()

        concise = self._should_be_concise(input.query)
        if concise:
            detail_guidance = (
                "The user requested a brief response. Keep it tight (around 4-6 sentences), "
                "focus on the key facts, and still include citations."
            )
        else:
            detail_guidance = (
                "Provide a research-style response with context, key points, and implications or "
                "limitations. Aim for multiple paragraphs or labeled sections while staying grounded "
                "in the sources."
            )

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

    async def run_stream(self, input: AgentInput):
        """
        Synthesize an answer with streaming output.

        Yields chunks of the answer as they're generated.
        Final yield is the complete AgentOutput.
        """
        start_time = time.perf_counter()

        concise = self._should_be_concise(input.query)
        if concise:
            detail_guidance = (
                "The user requested a brief response. Keep it tight (around 4-6 sentences), "
                "focus on the key facts, and still include citations."
            )
        else:
            detail_guidance = (
                "Provide a research-style response with context, key points, and implications or "
                "limitations. Aim for multiple paragraphs or labeled sections while staying grounded "
                "in the sources."
            )

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

        context_text = "\n\n---\n\n".join(context_parts)

        # Build the prompt for streaming (markdown output, not JSON)
        prompt = f"""Answer this research question based on the provided context:

Question: {input.query}

Response detail guidance: {detail_guidance}

Context:
{context_text}

Write a well-formatted markdown answer with inline [Source N] citations."""

        # Stream the answer
        full_answer = ""
        full_thoughts = ""
        try:
            async for chunk in self.gemini.generate_stream(
                prompt=prompt,
                system_instruction=SYNTHESIS_STREAMING_PROMPT,
                temperature=0.5,
                max_tokens=3072,
                include_thoughts=True,
            ):
                chunk_type = chunk.get("type", "text")
                chunk_content = chunk.get("content", "")

                if chunk_type == "thought":
                    full_thoughts += chunk_content
                    yield {"type": "thought_chunk", "content": chunk_content}
                elif chunk_type == "text":
                    full_answer += chunk_content
                    yield {"type": "answer_chunk", "content": chunk_content}
        except Exception as e:
            logger.error(f"[{self.name}] Streaming error: {e}")
            full_answer = (
                "I apologize, but I encountered an issue generating a response. "
                "Please try again."
            )
            yield {"type": "answer_chunk", "content": full_answer}

        latency = int((time.perf_counter() - start_time) * 1000)

        # Extract sources used from the answer (look for [Source N] patterns)
        import re

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
