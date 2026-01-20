"""Retrieval Agent - Executes hybrid RAG search."""

import time
from uuid import UUID

from app.agents.base import BaseAgent, AgentInput, AgentOutput
from app.services.search import get_search_service


class RetrievalAgent(BaseAgent):
    """Agent that retrieves relevant context from internal documents."""

    name = "retrieval"

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.search_service = get_search_service()

    async def run(self, input: AgentInput) -> AgentOutput:
        """Execute hybrid search and return relevant chunks."""
        start_time = time.perf_counter()

        # Extract search parameters
        top_k = input.constraints.get("max_sources", 10)
        document_ids = input.context.get("document_ids")

        # Execute hybrid search
        results = await self.search_service.search(
            query=input.query,
            user_id=UUID(self.user_id),
            top_k=top_k,
            document_ids=[UUID(d) for d in document_ids] if document_ids else None,
        )

        # Format results for downstream agents
        formatted_results = [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "content": r.content,
                "metadata": r.metadata,
                "score": r.combined_score,
            }
            for r in results
        ]

        latency = int((time.perf_counter() - start_time) * 1000)

        return AgentOutput(
            agent_name=self.name,
            result=formatted_results,
            metadata={
                "total_results": len(results),
                "top_k": top_k,
            },
            latency_ms=latency,
        )
