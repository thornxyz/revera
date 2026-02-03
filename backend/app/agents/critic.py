"""Critic Agent - Verifies claims against sources."""

import time
import json
import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


CRITIC_SYSTEM_PROMPT = """You are a research verification agent. Your job is to verify that claims in an answer are supported by the provided sources.

For each claim in the answer:
1. Check if it is supported by the cited source
2. Check if the citation is accurate  
3. Flag any unsupported or hallucinated statements
4. Assess source quality and potential conflicts
5. Check for missing important information

Output format:
{
    "verification_status": "verified|partial|unverified",
    "confidence_score": 0.0-1.0,
    "verified_claims": [
        {"claim": "The claim text", "source": 1, "status": "verified", "strength": "strong|moderate|weak"}
    ],
    "unsupported_claims": [
        {"claim": "Unsupported claim", "reason": "Not found in sources", "severity": "critical|moderate|minor"}
    ],
    "conflicting_information": [
        {"topic": "What conflicts", "source1": 1, "source2": 3, "description": "How they conflict"}
    ],
    "source_quality": {
        "internal_sources": {"count": 0, "reliability": "high|medium|low"},
        "web_sources": {"count": 0, "reliability": "high|medium|low", "recency": "recent|moderate|dated"}
    },
    "missing_citations": [
        {"statement": "Statement without citation", "suggestion": "Could cite source N"}
    ],
    "coverage_gaps": [
        "Important aspect not addressed in sources"
    ],
    "overall_assessment": "Brief assessment of answer quality and reliability"
}

Be strict. If something isn't explicitly stated in sources, mark it as unsupported.
Consider source recency, authority, and potential biases.
"""


class CriticAgent(BaseAgent):
    """Agent that verifies claims in synthesized answers."""

    name = "critic"

    def __init__(self):
        self.gemini = get_gemini_client()

    async def run(self, input: AgentInput) -> AgentOutput:
        """Verify the synthesized answer against sources with quality assessment."""
        start_time = time.perf_counter()

        # Get the answer and sources from context
        synthesis_result = input.context.get("synthesis_result", {})
        answer = synthesis_result.get("answer", "")
        source_map = synthesis_result.get("source_map", {})

        internal_sources = input.context.get("internal_sources", [])
        web_sources = input.context.get("web_sources", [])

        # Build sources text with metadata for verification
        sources_text = []
        all_sources = internal_sources + web_sources
        for i, source in enumerate(all_sources, start=1):
            content = source.get("content", "")
            source_type = "Internal Document" if i <= len(internal_sources) else "Web"

            # Add metadata for web sources
            metadata = ""
            if source_type == "Web":
                url = source.get("url", "")
                date = source.get("date", "Unknown date")
                score = source.get("relevance_score", source.get("score", 0))
                metadata = f" (URL: {url}, Date: {date}, Score: {score:.2f})"

            sources_text.append(
                f"[Source {i}] ({source_type}{metadata}):\n{content[:1500]}"
            )  # More context for better verification

        # Build verification prompt with original query for context
        prompt = f"""Verify this answer against the provided sources:

Original Question: {input.query}

Answer to verify:
{answer}

Available Sources:
{chr(10).join(sources_text)}

Perform thorough verification:
1. Check each claim against sources
2. Assess source quality and recency
3. Identify any conflicts between sources
4. Note any coverage gaps
5. Verify citation accuracy

Output verification results in JSON format."""

        # Run verification with async method (respects asyncio cancellation)
        response = await self.gemini.generate_json_async(
            prompt=prompt,
            system_instruction=CRITIC_SYSTEM_PROMPT,
            temperature=0.1,  # Lower for more consistent verification
        )

        # Parse response with error handling
        try:
            result = self._parse_json_response(response)

            # Validate required fields
            if "verification_status" not in result:
                logger.warning(
                    f"[{self.name}] Missing verification_status, setting to 'partial'"
                )
                result["verification_status"] = "partial"

            if "confidence_score" not in result:
                result["confidence_score"] = 0.5

            if "overall_assessment" not in result:
                result["overall_assessment"] = (
                    "Verification completed with limited information"
                )

        except json.JSONDecodeError as e:
            logger.error(
                f"[{self.name}] Failed to parse critic response: {e}\n"
                f"Response length: {len(response)}\n"
                f"Response preview: {response[:500]}"
            )

            # Return a safe default verification result
            result = {
                "verification_status": "unverified",
                "confidence_score": 0.0,
                "verified_claims": [],
                "unsupported_claims": [],
                "conflicting_information": [],
                "source_quality": {
                    "internal_sources": {
                        "count": len(internal_sources),
                        "reliability": "unknown",
                    },
                    "web_sources": {
                        "count": len(web_sources),
                        "reliability": "unknown",
                        "recency": "unknown",
                    },
                },
                "missing_citations": [],
                "coverage_gaps": [],
                "overall_assessment": "Unable to complete verification due to technical error",
                "error": "json_parse_error",
            }

        # Add metadata
        result["sources_breakdown"] = {
            "internal_count": len(internal_sources),
            "web_count": len(web_sources),
            "total": len(all_sources),
        }

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=result,
            metadata={
                "sources_checked": len(all_sources),
                "internal_sources": len(internal_sources),
                "web_sources": len(web_sources),
            },
            latency_ms=latency,
        )
