"""Documents API routes."""

import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from uuid import UUID

from app.services.ingestion import get_ingestion_service
from app.services.image_ingestion import (
    get_image_ingestion_service,
    SUPPORTED_IMAGE_TYPES,
)
from app.services.title_generator import generate_title_from_filename
from app.core.auth import get_current_user_id


router = APIRouter()
logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class DocumentResponse(BaseModel):
    """Response for document operations."""

    id: str
    filename: str
    type: str = "pdf"  # "pdf" or "image"
    chat_id: str | None
    image_url: str | None = None
    created_at: str


class DocumentListResponse(BaseModel):
    """Response for listing documents."""

    documents: list[DocumentResponse]
    total: int


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    chat_id: str | None = Query(
        None,
        description="Chat ID to associate document with (auto-creates if not provided)",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload and ingest a document or image (chat-scoped).

    Supports: PDF files, PNG, JPG, JPEG, WebP, GIF images.

    The document/image will be:
    1. For PDFs: Text extracted, chunked, and embedded
    2. For Images: Described via Gemini Vision, embedded, stored in Supabase Storage
    3. Indexed in vector database for RAG retrieval
    4. Linked to the specified chat (or auto-created chat)

    If no chat_id is provided, a new chat will be automatically created
    with a title based on the filename.
    """
    from app.core.database import get_supabase_client

    supabase = get_supabase_client()

    # Auto-create chat if not provided
    if not chat_id:
        # Generate title from filename
        chat_title = generate_title_from_filename(file.filename or "document.pdf")

        # Create new chat
        new_chat_id = str(uuid.uuid4())
        thread_id = f"chat-{new_chat_id}"

        logger.info(
            f"[DOC_UPLOAD] Auto-creating chat for document upload: title='{chat_title}'"
        )

        new_chat = (
            supabase.table("chats")
            .insert(
                {
                    "id": new_chat_id,
                    "user_id": user_id,
                    "title": chat_title,
                    "thread_id": thread_id,
                }
            )
            .execute()
        )

        if not new_chat.data:
            raise HTTPException(status_code=500, detail="Failed to create chat")

        chat_id = new_chat_id
        logger.info(f"[DOC_UPLOAD] Created chat {chat_id} with title: {chat_title}")
    else:
        # Validate chat ownership if chat_id was provided
        chat_check = (
            supabase.table("chats")
            .select("id")
            .eq("id", chat_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not chat_check.data:
            raise HTTPException(status_code=404, detail="Chat not found")

    # Validate filename exists
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a filename")

    # Determine file type
    filename_lower = file.filename.lower()
    file_ext = "." + filename_lower.rsplit(".", 1)[-1] if "." in filename_lower else ""

    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    is_image = file_ext in IMAGE_EXTENSIONS

    # Read file content
    content = await file.read()
    content_len = len(content)

    # Size limits: 50MB for PDFs, 10MB for images
    max_size = 10 * 1024 * 1024 if is_image else 50 * 1024 * 1024
    if content_len > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {max_size // (1024*1024)}MB)",
        )

    try:
        file_type = "image" if is_image else "pdf"
        logger.info(
            f"[DOC_UPLOAD] Starting {file_type} ingest",
            extra={
                "doc_filename": file.filename,
                "doc_user_id": user_id,
                "doc_chat_id": chat_id,
                "doc_bytes": content_len,
                "doc_type": file_type,
            },
        )

        if is_image:
            # Route to image ingestion service
            image_service = get_image_ingestion_service()
            mime_type = file.content_type or "image/jpeg"
            document_id = await image_service.ingest_image(
                file_content=content,
                filename=file.filename,
                mime_type=mime_type,
                user_id=UUID(user_id),
                chat_id=UUID(chat_id),
            )
        else:
            # Route to PDF ingestion service
            ingestion_service = get_ingestion_service()
            document_id = await ingestion_service.ingest_pdf(
                file_content=content,
                filename=file.filename,
                user_id=UUID(user_id),
                chat_id=UUID(chat_id),
            )

        # Get document details
        doc = (
            supabase.table("documents")
            .select("*")
            .eq("id", str(document_id))
            .single()
            .execute()
        )

        doc_data = doc.data if doc.data else {}
        return DocumentResponse(
            id=str(document_id),
            filename=str(doc_data.get("filename", "")),
            type=str(doc_data.get("type", "pdf")),
            chat_id=str(doc_data.get("chat_id")) if doc_data.get("chat_id") else None,
            image_url=(
                str(doc_data.get("image_url")) if doc_data.get("image_url") else None
            ),
            created_at=str(doc_data.get("created_at", "")),
        )
    except Exception as e:
        logger.exception(
            "[DOC_UPLOAD] Failed to ingest document",
            extra={
                "doc_filename": file.filename,
                "doc_user_id": user_id,
                "doc_chat_id": chat_id,
                "doc_bytes": content_len,
            },
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    chat_id: str | None = Query(None, description="Filter documents by chat ID"),
    user_id: str = Depends(get_current_user_id),
):
    """List documents for the current user, optionally filtered by chat."""
    from app.core.database import get_supabase_client

    supabase = get_supabase_client()

    # Build query
    query = supabase.table("documents").select("*").eq("user_id", user_id)

    # Apply chat filter if provided
    if chat_id:
        query = query.eq("chat_id", chat_id)

    result = query.order("created_at", desc=True).execute()

    documents_data = result.data or []
    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=str(doc.get("id", "")),
                filename=str(doc.get("filename", "")),
                type=str(doc.get("type", "pdf")),
                chat_id=str(doc.get("chat_id")) if doc.get("chat_id") else None,
                image_url=str(doc.get("image_url")) if doc.get("image_url") else None,
                created_at=str(doc.get("created_at", "")),
            )
            for doc in documents_data
        ],
        total=len(documents_data),
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a document (PDF or image) and all its associated data."""
    from app.core.database import get_supabase_client

    supabase = get_supabase_client()

    # Check document type first
    doc = (
        supabase.table("documents")
        .select("type")
        .eq("id", document_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not doc.data:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_type = doc.data.get("type", "pdf")

    if doc_type == "image":
        # Delete via image ingestion service
        image_service = get_image_ingestion_service()
        success = await image_service.delete_image(
            document_id=UUID(document_id),
            user_id=UUID(user_id),
        )
    else:
        # Delete via PDF ingestion service
        ingestion_service = get_ingestion_service()
        success = await ingestion_service.delete_document(
            document_id=UUID(document_id),
            user_id=UUID(user_id),
        )

    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "deleted", "document_id": document_id, "type": doc_type}
