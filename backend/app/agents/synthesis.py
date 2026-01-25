"""Synthesis Agent - Produces grounded answers from context."""

import re
import time

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client


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

        # Parse response
        result = self._parse_json_response(response)
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
