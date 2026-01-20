"""Critic Agent - Verifies claims against sources."""

import time

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client


CRITIC_SYSTEM_PROMPT = """You are a research verification agent. Your job is to verify that claims in an answer are supported by the provided sources.

For each claim in the answer:
1. Check if it is supported by the cited source
2. Check if the citation is accurate
3. Flag any unsupported or hallucinated statements

Output format:
{
    "verification_status": "verified|partial|unverified",
    "confidence_score": 0.0-1.0,
    "verified_claims": [
        {"claim": "The claim text", "source": 1, "status": "verified"}
    ],
    "unsupported_claims": [
        {"claim": "Unsupported claim", "reason": "Not found in sources"}
    ],
    "missing_citations": [
        {"statement": "Statement without citation", "suggestion": "Could cite source N"}
    ],
    "overall_assessment": "Brief assessment of answer quality"
}

Be strict. If something isn't explicitly stated in sources, mark it as unsupported.
"""


class CriticAgent(BaseAgent):
    """Agent that verifies claims in synthesized answers."""

    name = "critic"

    def __init__(self):
        self.gemini = get_gemini_client()

    async def run(self, input: AgentInput) -> AgentOutput:
        """Verify the synthesized answer against sources."""
        start_time = time.perf_counter()

        # Get the answer and sources from context
        synthesis_result = input.context.get("synthesis_result", {})
        answer = synthesis_result.get("answer", "")
        source_map = synthesis_result.get("source_map", {})

        internal_sources = input.context.get("internal_sources", [])
        web_sources = input.context.get("web_sources", [])

        # Build sources text for verification
        sources_text = []
        all_sources = internal_sources + web_sources
        for i, source in enumerate(all_sources, start=1):
            content = source.get("content", "")
            sources_text.append(
                f"[Source {i}]: {content[:1000]}"
            )  # Truncate for context window

        # Build verification prompt
        prompt = f"""Verify this answer against the provided sources:

Answer to verify:
{answer}

Available Sources:
{chr(10).join(sources_text)}

Check each claim and citation. Output verification results in JSON format."""

        # Run verification
        response = self.gemini.generate_json(
            prompt=prompt,
            system_instruction=CRITIC_SYSTEM_PROMPT,
            temperature=0.2,
        )

        # Parse response
        result = self._parse_json_response(response)

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=result,
            metadata={
                "sources_checked": len(all_sources),
            },
            latency_ms=latency,
        )
