"""Qdrant client wrapper and collection management."""

from qdrant_client import QdrantClient, models
from app.core.config import get_settings


class QdrantService:
    """Wrapper for Qdrant client and collection management."""

    def __init__(self):
        settings = get_settings()
        if not settings.qdrant_url:
            raise ValueError("QDRANT_URL is not set")

        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=True,
        )
        self.collection_name = "revera_documents"
        self._ensure_collection()

    def _ensure_collection(self):
        """Ensure the collection exists with correct vector configuration."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=3072,  # Gemini embedding-001 high-dim
                        distance=models.Distance.COSINE,
                    ),
                    "colbert": models.VectorParams(
                        size=128,  # Standard ColBERT size
                        distance=models.Distance.COSINE,
                        multivector_config=models.MultiVectorConfig(
                            comparator=models.MultiVectorComparator.MAX_SIM
                        ),
                    ),
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(),
                },
            )
            print(f"Created collection: {self.collection_name}")

            # Create payload indexes for filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            print("Created payload indexes for user_id and document_id")
        else:
            print(f"Using existing collection: {self.collection_name}")

    def get_client(self) -> QdrantClient:
        return self.client


# Singleton
_qdrant_service: QdrantService | None = None


def get_qdrant_service() -> QdrantService:
    """Get or create Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
