"""Base agent interface and common utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    """Standard input for all agents."""

    query: str
    context: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)


@dataclass
class AgentOutput:
    """Standard output from all agents."""

    agent_name: str
    result: Any
    metadata: dict = field(default_factory=dict)
    latency_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "agent_name": self.agent_name,
            "result": self.result,
            "metadata": self.metadata,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    name: str = "base"

    @abstractmethod
    async def run(self, input: AgentInput) -> AgentOutput:
        """Execute the agent logic."""
        pass

    def _parse_json_response(self, response: str) -> dict:
        """
        Safely parse JSON from LLM response with multiple fallback strategies.

        Strategies attempted in order:
        1. Direct JSON parse
        2. Extract from markdown code blocks
        3. Strip whitespace/BOM and retry
        4. Extract JSON object from mixed content
        5. Repair common JSON issues
        6. Extract key-value pairs manually

        Args:
            response: Raw string response from LLM

        Returns:
            Parsed dictionary, or raises JSONDecodeError with detailed context
        """
        if not response or not response.strip():
            logger.error(f"[{self.name}] Empty response from LLM")
            raise json.JSONDecodeError("Empty response", "", 0)

        original_response = response
        response_preview = response[:500] + ("..." if len(response) > 500 else "")

        # Strategy 1: Direct parse
        try:
            result = json.loads(response)
            logger.debug(f"[{self.name}] JSON parsed successfully (direct)")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"[{self.name}] Direct parse failed: {e}")

        # Strategy 2: Extract from markdown code blocks
        try:
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end > start:
                    extracted = response[start:end].strip()
                    result = json.loads(extracted)
                    logger.debug(
                        f"[{self.name}] JSON parsed successfully (markdown json)"
                    )
                    return result
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end > start:
                    extracted = response[start:end].strip()
                    result = json.loads(extracted)
                    logger.debug(
                        f"[{self.name}] JSON parsed successfully (markdown generic)"
                    )
                    return result
        except json.JSONDecodeError as e:
            logger.debug(f"[{self.name}] Markdown extraction failed: {e}")

        # Strategy 3: Strip whitespace, BOM, and invisible characters
        try:
            cleaned = response.strip().lstrip("\ufeff\ufffe")  # Remove BOM
            cleaned = re.sub(r"^\s+|\s+$", "", cleaned, flags=re.MULTILINE)
            result = json.loads(cleaned)
            logger.debug(f"[{self.name}] JSON parsed successfully (cleaned)")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"[{self.name}] Cleaned parse failed: {e}")

        # Strategy 4: Extract JSON object from mixed content using regex
        try:
            # Find the first complete JSON object
            json_pattern = r"\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}"
            matches = re.finditer(json_pattern, response, re.DOTALL)
            for match in matches:
                try:
                    extracted = match.group(0)
                    result = json.loads(extracted)
                    logger.debug(
                        f"[{self.name}] JSON parsed successfully (regex extraction)"
                    )
                    return result
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"[{self.name}] Regex extraction failed: {e}")

        # Strategy 5: Repair common JSON issues
        try:
            repaired = response.strip()

            # Fix trailing commas before closing brackets/braces
            repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)

            # Try to fix unescaped quotes in strings (heuristic approach)
            # This is tricky and may not work for all cases
            # We look for quotes that aren't properly escaped
            # Note: This is a simplified approach and may have edge cases

            # If response ends mid-string or mid-object, try to close it
            if repaired.count("{") > repaired.count("}"):
                repaired += "}" * (repaired.count("{") - repaired.count("}"))
            if repaired.count("[") > repaired.count("]"):
                repaired += "]" * (repaired.count("[") - repaired.count("]"))

            # Count quotes to see if we have an unterminated string
            # This is a simple heuristic that may help with truncation
            quote_count = repaired.count('"') - repaired.count('\\"')
            if quote_count % 2 != 0:
                # Odd number of quotes, try to close the string
                # Find the last quote and check if it's in a value position
                last_quote = repaired.rfind('"')
                if last_quote > 0 and repaired[last_quote - 1] != "\\":
                    # Add closing quote and try to close the object
                    repaired += '"'
                    if repaired.count("{") > repaired.count("}"):
                        repaired += "}" * (repaired.count("{") - repaired.count("}"))

            result = json.loads(repaired)
            logger.warning(
                f"[{self.name}] JSON parsed after repairs (may be incomplete)"
            )
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"[{self.name}] Repair strategy failed: {e}")

        # All strategies failed - log detailed error and raise
        logger.error(
            f"[{self.name}] All JSON parsing strategies failed.\n"
            f"Response length: {len(original_response)}\n"
            f"Response preview: {response_preview}\n"
            f"Last error: {e}"
        )

        # Re-raise the original error with context
        raise json.JSONDecodeError(
            f"Failed to parse JSON after trying all strategies. Response preview: {response_preview[:200]}",
            original_response,
            0,
        )
