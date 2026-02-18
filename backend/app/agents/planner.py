"""Planner Agent - Decomposes user queries into execution plans."""

import time
import json
import logging

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.agents.agent_models import ExecutionStep, ExecutionPlan
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


PLANNER_SYSTEM_PROMPT = """You are a research planning agent. Your job is to analyze user queries and create structured execution plans.

For each query, you must:
1. Break it down into subtasks
2. Decide which tools to use (rag, web, synthesis, verification, image_gen)
3. Define constraints and requirements

Available tools:
- rag: Search internal documents using hybrid retrieval
- web: Search the web for recent/external information
- synthesis: Combine retrieved information into an answer
- verification: Verify claims against sources
- image_gen: Generate an image from a text description (use when the user asks to create, generate, draw, design, or visualize an image)

Output a JSON plan with this exact structure:
{
    "subtasks": ["subtask1", "subtask2"],
    "steps": [
        {"tool": "rag", "description": "what to search for", "parameters": {}},
        {"tool": "web", "description": "what to search for", "parameters": {"freshness": "recent"}},
        {"tool": "synthesis", "description": "how to combine results", "parameters": {}},
        {"tool": "verification", "description": "what to verify", "parameters": {}},
        {"tool": "image_gen", "description": "what image to generate", "parameters": {}}
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
- Include image_gen step when the user explicitly or implicitly requests image creation/generation (e.g., "create an image", "draw", "generate a picture", "visualize", "show me what X looks like")
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

        # Get memory context if available
        memory_prompt = input.constraints.get("memory_prompt", "")
        memory_section = ""
        if memory_prompt:
            memory_section = (
                "\nPrevious conversation context:\n"
                f"{memory_prompt}\n\n"
                "Use this context to:\n"
                "- Recognize follow-up questions and maintain coherence\n"
                "- Avoid redundant searches for recently discussed topics\n"
                "- Adjust the plan based on what's already been retrieved\n"
            )

        # Build the prompt
        prompt = f"""Create an execution plan for this research query:

Query: {input.query}
{memory_section}
User preferences:
- Use web search: {input.constraints.get("use_web", True)}
- Require citations: {input.constraints.get("citations_required", True)}
- Preferred sources: {input.constraints.get("preferred_sources", "any")}

Output the plan as JSON."""

        # Generate plan
        response = self.gemini.generate_json(
            prompt=prompt,
            system_instruction=PLANNER_SYSTEM_PROMPT,
            temperature=0.3,
        )

        # Parse the response with error handling
        try:
            plan_dict = self._parse_json_response(response)

            # Validate required fields
            if "steps" not in plan_dict:
                logger.warning(
                    f"[{self.name}] Missing 'steps' field, creating default plan"
                )
                plan_dict["steps"] = [
                    {
                        "tool": "rag",
                        "description": "Search internal documents",
                        "parameters": {},
                    },
                    {
                        "tool": "synthesis",
                        "description": "Synthesize answer",
                        "parameters": {},
                    },
                ]

            if "subtasks" not in plan_dict:
                plan_dict["subtasks"] = ["Answer the user query"]

            if "constraints" not in plan_dict:
                plan_dict["constraints"] = {}

        except json.JSONDecodeError as e:
            logger.error(
                f"[{self.name}] Failed to parse planner response: {e}\n"
                f"Response length: {len(response)}\n"
                f"Response preview: {response[:500]}"
            )

            # Return a safe default plan
            plan_dict = {
                "subtasks": ["Answer the user query"],
                "steps": [
                    {
                        "tool": "rag",
                        "description": "Search internal documents",
                        "parameters": {},
                    },
                    {
                        "tool": "synthesis",
                        "description": "Synthesize answer",
                        "parameters": {},
                    },
                ],
                "constraints": {
                    "citations_required": True,
                    "max_sources": 10,
                },
            }

        # Convert to structured plan
        plan = ExecutionPlan(
            subtasks=plan_dict.get("subtasks", []),
            steps=[
                ExecutionStep(
                    tool=s.get("tool", "rag"),
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
