"""Document ingestion service - PDF parsing, chunking, and embedding."""

import io
from uuid import UUID

import fitz  # PyMuPDF

from app.core.database import get_supabase_client
from app.llm.gemini import get_gemini_client


class IngestionService:
    """Service for ingesting documents into the RAG system."""

    def __init__(self):
        self.supabase = get_supabase_client()
        self.gemini = get_gemini_client()
        self.chunk_size = 1000  # characters
        self.chunk_overlap = 200  # characters

    async def ingest_pdf(
        self,
        file_content: bytes,
        filename: str,
        user_id: UUID,
    ) -> UUID:
        """
        Ingest a PDF file: parse, chunk, embed, and store.

        Returns the document ID.
        """
        # 1. Create document record
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

        document_id = doc_result.data[0]["id"]

        # 2. Extract text from PDF
        text_pages = self._extract_pdf_text(file_content)

        # 3. Chunk the text
        chunks = self._chunk_text(text_pages)

        # 4. Generate embeddings
        chunk_texts = [c["content"] for c in chunks]
        embeddings = self.gemini.embed_texts(chunk_texts)

        # 5. Store chunks with embeddings
        chunk_records = [
            {
                "document_id": document_id,
                "content": chunk["content"],
                "embedding": embeddings[i],
                "metadata": chunk["metadata"],
            }
            for i, chunk in enumerate(chunks)
        ]

        # Insert in batches of 50
        for i in range(0, len(chunk_records), 50):
            batch = chunk_records[i : i + 50]
            self.supabase.table("document_chunks").insert(batch).execute()

        return UUID(document_id)

    def _extract_pdf_text(self, file_content: bytes) -> list[dict]:
        """Extract text from PDF with page numbers."""
        pdf_doc = fitz.open(stream=io.BytesIO(file_content), filetype="pdf")
        pages = []

        for page_num, page in enumerate(pdf_doc, start=1):
            text = page.get_text()
            if text.strip():
                pages.append(
                    {
                        "page": page_num,
                        "text": text,
                    }
                )

        pdf_doc.close()
        return pages

    def _chunk_text(self, pages: list[dict]) -> list[dict]:
        """
        Chunk text with overlap, preserving page metadata.
        Uses a simple character-based chunking strategy.
        """
        chunks = []

        for page in pages:
            text = page["text"]
            page_num = page["page"]

            # Simple chunking with overlap
            start = 0
            while start < len(text):
                end = start + self.chunk_size
                chunk_text = text[start:end]

                # Avoid cutting mid-word if possible
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
        """Delete a document and its chunks."""
        # RLS will ensure only owner can delete
        result = (
            self.supabase.table("documents")
            .delete()
            .eq("id", str(document_id))
            .eq("user_id", str(user_id))
            .execute()
        )

        return len(result.data) > 0


# Singleton
_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    """Get or create ingestion service instance."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService()
    return _ingestion_service
