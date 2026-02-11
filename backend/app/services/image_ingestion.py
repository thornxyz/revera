"""Image ingestion service - Upload, describe, embed, and store images."""

import asyncio
import logging
import uuid
from typing import Any, cast
from uuid import UUID

from fastembed import SparseTextEmbedding, LateInteractionTextEmbedding
from qdrant_client import models

from app.core.config import get_settings
from app.core.database import get_supabase_client
from app.core.qdrant import get_qdrant_service
from app.llm.gemini import get_gemini_client

logger = logging.getLogger(__name__)

# Supported image MIME types
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# Maximum image size (10MB)
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class ImageIngestionService:
    """Service for ingesting images into the RAG system."""

    def __init__(self):
        self.settings = get_settings()
        self.supabase = get_supabase_client()
        self.gemini = get_gemini_client()
        self.qdrant = get_qdrant_service()
        self.storage_bucket = "images"

        # Initialize Local Models (for text description embeddings)
        self.colbert_model = LateInteractionTextEmbedding(
            model_name="colbert-ir/colbertv2.0",
            cache_dir="./models_cache",
        )
        self.sparse_model = SparseTextEmbedding(
            model_name="Qdrant/bm25",
            cache_dir="./models_cache",
        )

    async def ingest_image(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        user_id: UUID,
        chat_id: UUID | None = None,
    ) -> UUID:
        """
        Ingest an image: describe, embed, store in Supabase Storage, and index in Qdrant.

        Returns the document ID.
        """
        # Validate MIME type
        if mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ValueError(f"Unsupported image type: {mime_type}")

        # Validate file size
        if len(file_content) > MAX_IMAGE_SIZE:
            raise ValueError(
                f"Image too large. Maximum size is {MAX_IMAGE_SIZE // (1024*1024)}MB"
            )

        # 1. Upload image to Supabase Storage first
        storage_path = await self._store_image(
            file_content, filename, user_id, mime_type
        )
        logger.info(f"[IMAGE_INGEST] Stored image at: {storage_path}")

        # 2. Generate image description using Gemini Vision
        try:
            description = await self.gemini.generate_image_description(
                image_bytes=file_content,
                mime_type=mime_type,
            )
            logger.info(
                f"[IMAGE_INGEST] Generated description: {len(description)} chars"
            )
        except Exception as e:
            # Clean up storage on failure
            await self._delete_from_storage(storage_path)
            raise RuntimeError(f"Failed to generate image description: {e}") from e

        # 3. Create document record in Supabase
        try:
            doc_data = {
                "user_id": str(user_id),
                "filename": filename,
                "type": "image",
                "image_url": storage_path,
                "metadata": {
                    "mime_type": mime_type,
                    "size_bytes": len(file_content),
                    "description_preview": description[:500] if description else None,
                },
            }
            if chat_id:
                doc_data["chat_id"] = str(chat_id)

            doc_result = self.supabase.table("documents").insert(doc_data).execute()
        except Exception as e:
            await self._delete_from_storage(storage_path)
            logger.exception("[IMAGE_INGEST] Failed to create document record")
            raise

        doc_data = cast(list[dict[str, Any]], doc_result.data or [])
        if not doc_data:
            await self._delete_from_storage(storage_path)
            raise ValueError("Failed to create document record")

        document_id = str(doc_data[0]["id"]) if "id" in doc_data[0] else ""
        if not document_id:
            await self._delete_from_storage(storage_path)
            raise ValueError("Document ID not returned from database")

        # 4. Generate embeddings from description (for RAG search)
        try:
            # Run embedding generation in parallel
            async def generate_dense():
                return await self.gemini.embed_texts_async([description])

            async def generate_colbert():
                return await asyncio.to_thread(
                    lambda: list(self.colbert_model.embed([description]))
                )

            async def generate_sparse():
                return await asyncio.to_thread(
                    lambda: list(self.sparse_model.embed([description]))
                )

            (
                dense_embeddings,
                colbert_embeddings,
                sparse_embeddings,
            ) = await asyncio.gather(
                generate_dense(),
                generate_colbert(),
                generate_sparse(),
            )

            logger.info("[IMAGE_INGEST] Generated embeddings for image description")

            # 5. Prepare point for Qdrant
            colbert_vectors = (
                colbert_embeddings[0].tolist()
                if hasattr(colbert_embeddings[0], "tolist")
                else colbert_embeddings[0]
            )
            sparse_vec = sparse_embeddings[0]

            payload = {
                "document_id": document_id,
                "user_id": str(user_id),
                "content": description,
                "type": "image",
                "image_url": storage_path,
                "filename": filename,
                "metadata": {
                    "mime_type": mime_type,
                },
            }

            vector = cast(
                Any,
                {
                    "dense": dense_embeddings[0],
                    "colbert": colbert_vectors,
                    "sparse": models.SparseVector(
                        indices=sparse_vec.indices.tolist(),
                        values=sparse_vec.values.tolist(),
                    ),
                },
            )

            point = models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload,
            )

            # 6. Upsert to Qdrant
            self.qdrant.get_client().upsert(
                collection_name=self.qdrant.collection_name,
                points=[point],
            )

            logger.info(f"[IMAGE_INGEST] Indexed image in Qdrant: {document_id}")
            return UUID(hex=document_id)

        except Exception as e:
            # Rollback on failure
            logger.error(f"[IMAGE_INGEST] Embedding/indexing failed: {e}")
            await self._delete_from_storage(storage_path)
            self.supabase.table("documents").delete().eq("id", document_id).execute()
            raise

    async def save_generated_image(
        self,
        image_bytes: bytes,
        user_id: UUID,
        prompt: str,
    ) -> str:
        """
        Store a generated image in Supabase Storage and return the path.

        Args:
            image_bytes: Raw bytes of the generated image
            user_id: ID of the user who generated it
            prompt: The prompt used to generate it (for filename)

        Returns:
            Storage path (e.g. users/{user_id}/images/{uuid}.png)
        """
        # Clean prompt for filename
        clean_prompt = "".join(
            c for c in prompt[:30] if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        clean_prompt = clean_prompt.replace(" ", "_")
        if not clean_prompt:
            clean_prompt = "generated"

        unique_filename = f"{uuid.uuid4()}_{clean_prompt}.png"
        storage_path = f"users/{user_id}/images/{unique_filename}"

        try:
            self.supabase.storage.from_(self.storage_bucket).upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": "image/png"},
            )
            return storage_path
        except Exception as e:
            logger.error(f"[IMAGE_INGEST] Storage upload failed: {e}")
            raise

    async def _store_image(
        self,
        file_content: bytes,
        filename: str,
        user_id: UUID,
        mime_type: str,
    ) -> str:
        """Store image in Supabase Storage and return the path."""
        # Generate unique path: users/{user_id}/images/{uuid}_{filename}
        ext = SUPPORTED_IMAGE_TYPES.get(mime_type, ".jpg")
        unique_filename = f"{uuid.uuid4()}{ext}"
        storage_path = f"users/{user_id}/images/{unique_filename}"

        try:
            self.supabase.storage.from_(self.storage_bucket).upload(
                path=storage_path,
                file=file_content,
                file_options={"content-type": mime_type},
            )
            return storage_path
        except Exception as e:
            logger.error(f"[IMAGE_INGEST] Storage upload failed: {e}")
            raise

    async def _delete_from_storage(self, storage_path: str) -> None:
        """Delete an image from Supabase Storage."""
        try:
            self.supabase.storage.from_(self.storage_bucket).remove([storage_path])
        except Exception as e:
            logger.warning(f"[IMAGE_INGEST] Failed to clean up storage: {e}")

    def get_image_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Get a signed URL for an image in storage."""
        try:
            result = self.supabase.storage.from_(self.storage_bucket).create_signed_url(
                path=storage_path,
                expires_in=expires_in,
            )
            return result.get("signedURL", "")
        except Exception as e:
            logger.error(f"[IMAGE_INGEST] Failed to create signed URL: {e}")
            return ""

    async def get_image_bytes(self, storage_path: str) -> bytes | None:
        """Download image bytes from storage for multimodal synthesis."""
        try:
            response = self.supabase.storage.from_(self.storage_bucket).download(
                storage_path
            )
            return response
        except Exception as e:
            logger.error(f"[IMAGE_INGEST] Failed to download image: {e}")
            return None

    async def delete_image(self, document_id: UUID, user_id: UUID) -> bool:
        """Delete an image document and its associated data."""
        # Get document to find storage path
        doc = (
            self.supabase.table("documents")
            .select("*")
            .eq("id", str(document_id))
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )

        if not doc.data:
            return False

        storage_path = doc.data.get("image_url")

        # Delete from Supabase Storage
        if storage_path:
            await self._delete_from_storage(storage_path)

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

        # Delete from Supabase
        self.supabase.table("documents").delete().eq("id", str(document_id)).eq(
            "user_id", str(user_id)
        ).execute()

        logger.info(f"[IMAGE_INGEST] Deleted image: {document_id}")
        return True


# Singleton
_image_ingestion_service: ImageIngestionService | None = None


def get_image_ingestion_service() -> ImageIngestionService:
    """Get or create image ingestion service instance."""
    global _image_ingestion_service
    if _image_ingestion_service is None:
        _image_ingestion_service = ImageIngestionService()
    return _image_ingestion_service
