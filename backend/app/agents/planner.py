"""Planner Agent - Decomposes user queries into execution plans."""

import time
from dataclasses import dataclass

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.llm.gemini import get_gemini_client


@dataclass
class PlanStep:
    """A single step in the execution plan."""

    tool: str  # "rag", "web", "synthesis", "verification"
    description: str
    parameters: dict


@dataclass
class ExecutionPlan:
    """The complete execution plan for a query."""

    subtasks: list[str]
    steps: list[PlanStep]
    constraints: dict


PLANNER_SYSTEM_PROMPT = """You are a research planning agent. Your job is to analyze user queries and create structured execution plans.

For each query, you must:
1. Break it down into subtasks
2. Decide which tools to use (rag, web, synthesis, verification)
3. Define constraints and requirements

Available tools:
- rag: Search internal documents using hybrid retrieval
- web: Search the web for recent/external information
- synthesis: Combine retrieved information into an answer
- verification: Verify claims against sources

Output a JSON plan with this exact structure:
{
    "subtasks": ["subtask1", "subtask2"],
    "steps": [
        {"tool": "rag", "description": "what to search for", "parameters": {}},
        {"tool": "web", "description": "what to search for", "parameters": {"freshness": "recent"}},
        {"tool": "synthesis", "description": "how to combine results", "parameters": {}},
        {"tool": "verification", "description": "what to verify", "parameters": {}}
    ],
    "constraints": {
        "citations_required": true,
        "max_sources": 10,
        "prefer_internal": true
    }
}

Rules:
- Always include synthesis step
- Include verification for factual claims
- Use web search only when internal docs may be insufficient
- Be specific in descriptions
"""


class PlannerAgent(BaseAgent):
    """Agent that creates execution plans from user queries."""

    name = "planner"

    def __init__(self):
        self.gemini = get_gemini_client()

    async def run(self, input: AgentInput) -> AgentOutput:
        """Create an execution plan for the query."""
        start_time = time.perf_counter()

        # Build the prompt
        prompt = f"""Create an execution plan for this research query:

Query: {input.query}

User preferences:
- Use web search: {input.constraints.get('use_web', True)}
- Require citations: {input.constraints.get('citations_required', True)}
- Preferred sources: {input.constraints.get('preferred_sources', 'any')}

Output the plan as JSON."""

        # Generate plan
        response = self.gemini.generate_json(
            prompt=prompt,
            system_instruction=PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )

        # Parse the response
        plan_dict = self._parse_json_response(response)

        # Convert to structured plan
        plan = ExecutionPlan(
            subtasks=plan_dict.get("subtasks", []),
            steps=[
                PlanStep(
                    tool=s.get("tool", ""),
                    description=s.get("description", ""),
                    parameters=s.get("parameters", {}),
                )
                for s in plan_dict.get("steps", [])
            ],
            constraints=plan_dict.get("constraints", {}),
        )

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=plan,
            metadata={"raw_response": response},
            latency_ms=latency,
        )
