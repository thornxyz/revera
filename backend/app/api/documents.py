"""Documents API routes."""

import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from uuid import UUID

from app.services.ingestion import get_ingestion_service
from app.services.title_generator import generate_title_from_filename
from app.core.auth import get_current_user_id


router = APIRouter()
logger = logging.getLogger(__name__)


class DocumentResponse(BaseModel):
    """Response for document operations."""

    id: str
    filename: str
    chat_id: str | None
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
    Upload and ingest a PDF document (chat-scoped).

    The document will be:
    1. Parsed and text extracted
    2. Split into chunks
    3. Embedded using Gemini
    4. Stored in the vector database
    5. Linked to the specified chat (or auto-created chat)

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

    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file content
    content = await file.read()
    content_len = len(content)

    if content_len > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        logger.info(
            "[DOC_UPLOAD] Starting ingest",
            extra={
                "doc_filename": file.filename,
                "doc_user_id": user_id,
                "doc_chat_id": chat_id,
                "doc_bytes": content_len,
            },
        )
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
            chat_id=str(doc_data.get("chat_id")) if doc_data.get("chat_id") else None,
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
                chat_id=str(doc.get("chat_id")) if doc.get("chat_id") else None,
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
    """Delete a document and all its chunks."""
    ingestion_service = get_ingestion_service()
    success = await ingestion_service.delete_document(
        document_id=UUID(document_id),
        user_id=UUID(user_id),
    )

    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "deleted", "document_id": document_id}
