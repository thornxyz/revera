"""Hybrid search service - Dense (Gemini) + Sparse (BM25) + Late Interaction (ColBERT)."""

import asyncio
import logging
from uuid import UUID
from dataclasses import dataclass

from fastembed import SparseTextEmbedding, LateInteractionTextEmbedding
from qdrant_client import models

from app.core.qdrant import get_qdrant_service
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


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
    Triple Hybrid Search with RRF Fusion:
    1. Dense (Gemini) - Semantic understanding
    2. Sparse (BM25) - Keyword matching
    3. Late Interaction (ColBERT) - Fine-grained token matching

    Features:
    - Query rewriting for better retrieval
    - Reciprocal Rank Fusion (RRF) for score normalization
    - Parallel query embedding generation
    """

    # RRF constant (standard value from literature)
    RRF_K = 60

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

    async def rewrite_query_for_retrieval(self, query: str) -> str:
        """
        Rewrite a conversational query into an optimized retrieval query.

        This improves accuracy by transforming questions like "how does it compare?"
        into explicit search terms like "comparison of X and Y features".
        """
        prompt = f"""Rewrite this user query into an optimized search query for document retrieval.

Original query: {query}

Rules:
1. Expand pronouns and references to explicit terms
2. Include key concepts and synonyms
3. Remove conversational filler words
4. Keep it concise (under 20 words)
5. Focus on retrievable facts and entities

Output only the rewritten query, nothing else."""

        try:
            rewritten = self.gemini.generate(
                prompt=prompt,
                max_tokens=100,
            ).strip()
            if rewritten and len(rewritten) > 5:
                logger.debug(f"Query rewritten: '{query}' -> '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}")

        return query  # Fallback to original

    async def search_with_rrf(
        self,
        query: str,
        user_id: UUID,
        top_k: int = 10,
        document_ids: list[UUID] | None = None,
        rewrite_query: bool = True,
    ) -> list[SearchResult]:
        """
        Perform hybrid search with explicit Reciprocal Rank Fusion (RRF).

        This method:
        1. Optionally rewrites the query for better retrieval
        2. Runs Dense and Sparse searches separately
        3. Applies RRF to combine and normalize rankings
        4. Returns results with unified scores

        RRF Formula: score = sum(1 / (k + rank_i)) for each retriever i
        """
        # Optionally rewrite query for better retrieval accuracy
        search_query = query
        if rewrite_query:
            search_query = await self.rewrite_query_for_retrieval(query)

        # Generate query embeddings in parallel
        async def get_dense_embedding():
            return self.gemini.embed_text(search_query)

        async def get_sparse_embedding():
            sparse_gen = await asyncio.to_thread(
                lambda: list(self.sparse_model.query_embed(search_query))[0]
            )
            return models.SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist(),
            )

        dense_query, sparse_query = await asyncio.gather(
            get_dense_embedding(),
            get_sparse_embedding(),
        )

        # Build filter
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

        # Execute separate searches for RRF
        candidate_limit = top_k * 3  # Get more candidates for fusion

        # Dense search
        dense_results = self.qdrant.get_client().query_points(
            collection_name=self.qdrant.collection_name,
            query=dense_query,
            using="dense",
            query_filter=filter_,
            limit=candidate_limit,
        )

        # Sparse search
        sparse_results = self.qdrant.get_client().query_points(
            collection_name=self.qdrant.collection_name,
            query=sparse_query,
            using="sparse",
            query_filter=filter_,
            limit=candidate_limit,
        )

        # Apply RRF fusion
        rrf_scores: dict[str, float] = {}
        point_data: dict[str, dict] = {}

        # Process dense results
        for rank, point in enumerate(dense_results.points, start=1):
            point_id = str(point.id)
            rrf_scores[point_id] = rrf_scores.get(point_id, 0) + 1 / (self.RRF_K + rank)
            if point_id not in point_data:
                point_data[point_id] = {
                    "payload": point.payload or {},
                    "dense_score": point.score,
                }
            else:
                point_data[point_id]["dense_score"] = point.score

        # Process sparse results
        for rank, point in enumerate(sparse_results.points, start=1):
            point_id = str(point.id)
            rrf_scores[point_id] = rrf_scores.get(point_id, 0) + 1 / (self.RRF_K + rank)
            if point_id not in point_data:
                point_data[point_id] = {
                    "payload": point.payload or {},
                    "sparse_score": point.score,
                }
            else:
                point_data[point_id]["sparse_score"] = point.score

        # Sort by RRF score and return top_k
        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )

        search_results = []
        for point_id in sorted_ids[:top_k]:
            data = point_data[point_id]
            payload = data["payload"]
            search_results.append(
                SearchResult(
                    chunk_id=point_id,
                    document_id=str(payload.get("document_id", "")),
                    content=str(payload.get("content", "")),
                    metadata={
                        **payload.get("metadata", {}),
                        "rrf_score": rrf_scores[point_id],
                        "dense_score": data.get("dense_score"),
                        "sparse_score": data.get("sparse_score"),
                    },
                    score=rrf_scores[point_id],
                )
            )

        logger.info(
            f"RRF search complete: {len(search_results)} results "
            f"(dense: {len(dense_results.points)}, sparse: {len(sparse_results.points)})"
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
