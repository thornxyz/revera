"""Hybrid search service - Dense (Gemini) + Sparse (BM25) + Late Interaction (ColBERT)."""

from uuid import UUID
from dataclasses import dataclass

from fastembed import SparseTextEmbedding, LateInteractionTextEmbedding
from qdrant_client import models

from app.core.qdrant import get_qdrant_service
from app.llm.gemini import get_gemini_client


@dataclass
class SearchResult:
    """A single search result with scores."""

    chunk_id: str
    document_id: str
    content: str
    metadata: dict
    score: float


class HybridSearchService:
    """
    Triple Hybrid Search:
    1. Dense (Gemini)
    2. Sparse (BM25)
    3. Late Interaction (ColBERT)
    """

    def __init__(self):
        self.qdrant = get_qdrant_service()
        self.gemini = get_gemini_client()

        # Initialize Local Models for Query Embedding
        self.colbert_model = LateInteractionTextEmbedding(
            model_name="colbert-ir/colbertv2.0",
            cache_dir="./models_cache",
        )
        self.sparse_model = SparseTextEmbedding(
            model_name="Qdrant/bm25",
            cache_dir="./models_cache",
        )

    async def search(
        self,
        query: str,
        user_id: UUID,
        top_k: int = 10,
        document_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """
        Perform 3-way hybrid search using Qdrant.
        """
        # 1. Generate Query Embeddings
        # A. Dense (Gemini)
        dense_query = self.gemini.embed_text(query)

        # B. Sparse (BM25)
        # fastembed returns generator
        sparse_gen = list(self.sparse_model.query_embed(query))[0]
        sparse_query = models.SparseVector(
            indices=sparse_gen.indices.tolist(),
            values=sparse_gen.values.tolist(),
        )

        # C. Late Interaction (ColBERT)
        colbert_gen = list(self.colbert_model.query_embed(query))[0]
        # Ensure it's a list of vectors for ColBERT (Multi-Vector)
        colbert_query = (
            colbert_gen.tolist() if hasattr(colbert_gen, "tolist") else colbert_gen
        )

        # 2. Build Filter
        must_conditions: list[models.Condition] = [
            models.FieldCondition(
                key="user_id", match=models.MatchValue(value=str(user_id))
            )
        ]

        if document_ids:
            must_conditions.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=[str(d) for d in document_ids]),
                )
            )

        filter_ = models.Filter(must=must_conditions)

        # 3. Execute Search with Prefetch
        # Strategy:
        # - Prefetch with Dense (Semantic Candidate Generation)
        # - Prefetch with Sparse (Keyword Candidate Generation)
        # - Rescore with ColBERT (Late Interaction) using RRF or direct reranking via multivector

        # Note: Depending on Qdrant version, we can do
        # Query(ColBERT) -> Prefetch(Dense) + Prefetch(Sparse)

        # Let's try a robust prefetch strategy:
        # Retrieve candidates using Dense and Sparse, then rescore with ColBERT.

        prefetch = [
            models.Prefetch(
                query=dense_query,
                using="dense",
                limit=top_k * 2,
                filter=filter_,
            ),
            models.Prefetch(
                query=sparse_query,
                using="sparse",
                limit=top_k * 2,
                filter=filter_,
            ),
        ]

        results = self.qdrant.get_client().query_points(
            collection_name=self.qdrant.collection_name,
            prefetch=prefetch,
            query=colbert_query,
            using="colbert",
            limit=top_k,
        )

        # 4. Format Results
        search_results = []
        for point in results.points:
            payload = point.payload or {}
            search_results.append(
                SearchResult(
                    chunk_id=str(point.id),
                    document_id=str(payload.get("document_id", "")),
                    content=str(payload.get("content", "")),
                    metadata=payload.get("metadata", {}),
                    score=point.score,
                )
            )

        return search_results


# Singleton
_search_service: HybridSearchService | None = None


def get_search_service() -> HybridSearchService:
    """Get or create search service instance."""
    global _search_service
    if _search_service is None:
        _search_service = HybridSearchService()
    return _search_service
