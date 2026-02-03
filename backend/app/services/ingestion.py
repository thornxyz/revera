"""Document ingestion service - PDF parsing, chunking, and embedding."""

import asyncio
import io
import logging
import uuid
from typing import Any, cast
from uuid import UUID

import pymupdf
import pymupdf.layout
import pymupdf4llm
from fastembed import SparseTextEmbedding, LateInteractionTextEmbedding
from qdrant_client import models

from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.core.qdrant import get_qdrant_service
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)


class IngestionService:
    """Service for ingesting documents into the RAG system."""

    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase_client()
        self.gemini = get_gemini_client()
        self.qdrant = get_qdrant_service()
        self.chunk_size = 1000  # characters
        self.chunk_overlap = 200  # characters

        # Initialize Local Models
        # Late Interaction (ColBERT)
        self.colbert_model = LateInteractionTextEmbedding(
            model_name="colbert-ir/colbertv2.0",
            cache_dir="./models_cache",
        )
        # Sparse (BM25)
        self.sparse_model = SparseTextEmbedding(
            model_name="Qdrant/bm25",
            cache_dir="./models_cache",
        )

    async def ingest_pdf(
        self,
        file_content: bytes,
        filename: str,
        user_id: UUID,
    ) -> UUID:
        """
        Ingest a PDF file: parse, chunk, embed (Triple Vectors), and store in Qdrant.

        Returns the document ID.
        """
        # 1. Create document record in Supabase (Metadata Source of Truth)
        try:
            doc_result = (
                self.supabase.table("documents")
                .insert(
                    {
                        "user_id": str(user_id),
                        "filename": filename,
                        "metadata": {"type": "pdf"},
                    }
                )
                .execute()
            )
        except Exception:
            logger.exception(
                "[INGEST] Failed to create document record",
                extra={"filename": filename, "user_id": str(user_id)},
            )
            raise

        doc_data = cast(list[dict[str, Any]], doc_result.data or [])
        if not doc_data:
            logger.error(
                "[INGEST] No data returned after document insert",
                extra={"filename": filename, "user_id": str(user_id)},
            )
            raise ValueError("Failed to create document record")

        document_id = str(doc_data[0]["id"]) if "id" in doc_data[0] else ""
        if not document_id:
            raise ValueError("Document ID not returned from database")

        # 2. Extract text from PDF
        text_pages = self._extract_pdf_text(file_content)

        # 3. Chunk the text
        chunks = self._chunk_text(text_pages)
        if not chunks:
            return UUID(hex=document_id)

        chunk_texts = [c["content"] for c in chunks]

        # 4. Generate Embeddings (Triple Hybrid) - PARALLEL EXECUTION
        logger.info(f"Generating embeddings for {len(chunks)} chunks in parallel...")

        # Define async/threaded tasks for each embedding type
        async def generate_dense():
            """Dense embeddings via Gemini API (async network call)."""
            return await self.gemini.embed_texts_async(chunk_texts)

        async def generate_colbert():
            """ColBERT embeddings via local model (CPU-bound, run in thread)."""
            return await asyncio.to_thread(
                lambda: list(self.colbert_model.embed(chunk_texts))
            )

        async def generate_sparse():
            """Sparse BM25 embeddings via local model (CPU-bound, run in thread)."""
            return await asyncio.to_thread(
                lambda: list(self.sparse_model.embed(chunk_texts))
            )

        # Run all three embedding generations concurrently
        dense_embeddings, colbert_embeddings, sparse_embeddings = await asyncio.gather(
            generate_dense(),
            generate_colbert(),
            generate_sparse(),
        )

        logger.info("All embeddings generated successfully")

        # 5. Prepare Points for Qdrant
        points = []
        for i, chunk in enumerate(chunks):
            # Format Late Interaction for Qdrant (Multi-Vector)
            # FastEmbed returns list of numpy arrays for ColBERT
            colbert_vectors = (
                colbert_embeddings[i].tolist()
                if hasattr(colbert_embeddings[i], "tolist")
                else colbert_embeddings[i]
            )

            # Format Sparse for Qdrant
            sparse_vec = sparse_embeddings[i]

            payload = {
                "document_id": document_id,
                "user_id": str(user_id),
                "content": chunk["content"],
                "metadata": chunk["metadata"],
                "filename": filename,
            }

            vector = cast(
                Any,
                {
                    "dense": dense_embeddings[i],
                    "colbert": colbert_vectors,
                    "sparse": models.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
            )

            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )

        # 6. Upsert to Qdrant
        batch_size = self.settings.qdrant_upsert_batch_size
        if batch_size <= 0:
            batch_size = len(points)

        total_batches = max(1, (len(points) + batch_size - 1) // batch_size)
        print(f"Upserting {len(points)} points to Qdrant in {total_batches} batches...")
        try:
            for batch_index in range(0, len(points), batch_size):
                batch_number = batch_index // batch_size + 1
                batch_points = points[batch_index : batch_index + batch_size]
                print(
                    f"Upserting batch {batch_number}/{total_batches} ({len(batch_points)} points)..."
                )
                self.qdrant.get_client().upsert(
                    collection_name=self.qdrant.collection_name,
                    points=batch_points,
                )
            print("✅ Upsert complete!")
        except Exception as e:
            print(f"❌ Qdrant upsert failed: {e}")
            raise

        return UUID(hex=document_id)

    def _extract_pdf_text(self, file_content: bytes) -> list[dict]:
        """Extract markdown text from PDF with page numbers."""
        pdf_doc = pymupdf.open(stream=io.BytesIO(file_content), filetype="pdf")
        try:
            page_chunks = pymupdf4llm.to_markdown(
                pdf_doc,
                page_chunks=True,
                use_ocr=False,
            )
        finally:
            pdf_doc.close()

        pages = []
        if isinstance(page_chunks, list):
            for index, page_chunk in enumerate(page_chunks):
                text = str(page_chunk.get("text", ""))
                if not text.strip():
                    continue
                metadata = page_chunk.get("metadata", {})
                page_number = int(metadata.get("page_number", index + 1))
                pages.append(
                    {
                        "page": page_number,
                        "text": text,
                    }
                )

        return pages

    def _chunk_text(self, pages: list[dict]) -> list[dict]:
        """Chunk text with overlap, preserving page metadata."""
        chunks = []

        for page in pages:
            text = str(page["text"])
            page_num = int(page["page"])

            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunk_text: str = text[start:end]

                if end < len(text):
                    last_space = chunk_text.rfind(" ")
                    if last_space > self.chunk_size // 2:
                        chunk_text = chunk_text[:last_space]
                        end = start + last_space

                if chunk_text.strip():
                    chunks.append(
                        {
                            "content": chunk_text.strip(),
                            "metadata": {"page": page_num},
                        }
                    )

                start = end - self.chunk_overlap
                if start < 0:
                    start = 0
                if start >= len(text):
                    break

        return chunks

    async def delete_document(self, document_id: UUID, user_id: UUID) -> bool:
        """Delete a document and its vectors."""
        # Delete from Supabase
        result = (
            self.supabase.table("documents")
            .delete()
            .eq("id", str(document_id))
            .eq("user_id", str(user_id))
            .execute()
        )

        if result.data:
            # Delete from Qdrant
            self.qdrant.get_client().delete(
                collection_name=self.qdrant.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
            )
            return True

        return False


# Singleton
_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    """Get or create ingestion service instance."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service
