"""Hybrid search service - Dense (vector) + Sparse (keyword) retrieval."""

from uuid import UUID
from dataclasses import dataclass

from app.core.database import get_supabase_client
from app.llm.gemini import get_gemini_client


@dataclass
class SearchResult:
    """A single search result with scores."""

    chunk_id: str
    document_id: str
    content: str
    metadata: dict
    dense_score: float = 0.0
    sparse_score: float = 0.0
    combined_score: float = 0.0


class HybridSearchService:
    """
    Hybrid search combining dense (vector) and sparse (keyword) retrieval.

    Uses Reciprocal Rank Fusion (RRF) to combine results.
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.gemini = get_gemini_client()
        self.dense_weight = 0.6
        self.sparse_weight = 0.4
        self.rrf_k = 60  # RRF constant

    async def search(
        self,
        query: str,
        user_id: UUID,
        top_k: int = 10,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """
        Perform hybrid search across user's documents.

        Args:
            query: Search query
            user_id: User ID for document filtering
            top_k: Number of results to return
            document_ids: Optional list of document IDs to search within

        Returns:
            List of SearchResult objects ranked by combined score
        """
        # Get more candidates than needed for fusion
        candidate_k = top_k * 3

        # Run dense and sparse search in parallel
        dense_results = await self._dense_search(
            query, user_id, candidate_k, document_ids
        )
        sparse_results = await self._sparse_search(
            query, user_id, candidate_k, document_ids
        )

        # Fuse results using RRF
        fused = self._reciprocal_rank_fusion(dense_results, sparse_results)

        # Return top K
        return fused[:top_k]

    async def _dense_search(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Vector similarity search using embeddings."""
        # Generate query embedding
        query_embedding = self.gemini.embed_text(query)

        # Build the query - using pgvector similarity search
        # Note: This uses a Supabase RPC function for vector search
        params = {
            "query_embedding": query_embedding,
            "user_id_param": str(user_id),
            "match_count": top_k,
        }

        if document_ids:
            params["document_ids"] = [str(d) for d in document_ids]

        # Call the vector search RPC function
        result = self.supabase.rpc("match_document_chunks", params).execute()

        results = []
        for i, row in enumerate(result.data):
            results.append(
                SearchResult(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    metadata=row.get("metadata", {}),
                    dense_score=1
                    - row.get("distance", 0),  # Convert distance to similarity
                )
            )

        return results

    async def _sparse_search(
        self,
        query: str,
        user_id: UUID,
        top_k: int,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Keyword-based full-text search using Postgres FTS."""
        # Build the full-text search query
        # Format query for tsquery (replace spaces with &)
        ts_query = " & ".join(query.split())

        params = {
            "search_query": ts_query,
            "user_id_param": str(user_id),
            "match_count": top_k,
        }

        if document_ids:
            params["document_ids"] = [str(d) for d in document_ids]

        # Call the full-text search RPC function
        result = self.supabase.rpc("search_document_chunks_fts", params).execute()

        results = []
        for row in result.data:
            results.append(
                SearchResult(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    content=row["content"],
                    metadata=row.get("metadata", {}),
                    sparse_score=row.get("rank", 0),
                )
            )

        return results

    def _reciprocal_rank_fusion(
        self,
        dense_results: list[SearchResult],
        sparse_results: list[SearchResult],
    ) -> list[SearchResult]:
        """
        Combine results using Reciprocal Rank Fusion.

        RRF score = sum(1 / (k + rank)) for each result list
        """
        # Create a map of chunk_id -> SearchResult
        result_map: dict[str, SearchResult] = {}

        # Process dense results
        for rank, result in enumerate(dense_results, start=1):
            if result.chunk_id not in result_map:
                result_map[result.chunk_id] = result
            result_map[result.chunk_id].dense_score = 1 / (self.rrf_k + rank)

        # Process sparse results
        for rank, result in enumerate(sparse_results, start=1):
            if result.chunk_id not in result_map:
                result_map[result.chunk_id] = result
            result_map[result.chunk_id].sparse_score = 1 / (self.rrf_k + rank)

        # Calculate combined scores
        for result in result_map.values():
            result.combined_score = (
                self.dense_weight * result.dense_score
                + self.sparse_weight * result.sparse_score
            )

        # Sort by combined score
        fused = sorted(
            result_map.values(), key=lambda r: r.combined_score, reverse=True
        )

        return fused


# Singleton
_search_service: HybridSearchService | None = None


def get_search_service() -> HybridSearchService:
    """Get or create search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = HybridSearchService()
    return _search_service
