"""Retrieval Agent - Executes hybrid RAG search with RRF fusion."""

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
        """Execute hybrid search with RRF fusion and return relevant chunks."""
        start_time = time.perf_counter()

        # Extract search parameters
        top_k = input.constraints.get("max_sources", 10)
        document_ids = input.context.get("document_ids")
        # Allow disabling query rewriting via constraints if needed
        rewrite_query = input.constraints.get("rewrite_query", True)

        # Execute hybrid search with RRF fusion and query rewriting
        results = await self.search_service.search_with_rrf(
            query=input.query,
            user_id=UUID(self.user_id),
            top_k=top_k,
            document_ids=(
                [UUID(d) for d in document_ids] if document_ids is not None else None
            ),
            rewrite_query=rewrite_query,
        )

        # Format results for downstream agents
        formatted_results = [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "content": r.content,
                "metadata": r.metadata,
                "score": r.score,
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
                "query_rewritten": rewrite_query,
            },
            latency_ms=latency,
        )
