"""Base agent interface and common utilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import json


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
        """Safely parse JSON from LLM response."""
        try:
            # Try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end > start:
                    return json.loads(response[start:end].strip())
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end > start:
                    return json.loads(response[start:end].strip())
            raise
