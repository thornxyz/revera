"""Documents API routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from uuid import UUID

from app.services.ingestion import get_ingestion_service
from app.core.auth import get_current_user_id


router = APIRouter()
logger = logging.getLogger(__name__)


class DocumentResponse(BaseModel):
    """Response for document operations."""

    id: str
    filename: str
    created_at: str


class DocumentListResponse(BaseModel):
    """Response for listing documents."""

    documents: list[DocumentResponse]
    total: int


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload and ingest a PDF document.

    The document will be:
    1. Parsed and text extracted
    2. Split into chunks
    3. Embedded using Gemini
    4. Stored in the vector database
    """
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
                "doc_bytes": content_len,
            },
        )
        ingestion_service = get_ingestion_service()
        document_id = await ingestion_service.ingest_pdf(
            file_content=content,
            filename=file.filename,
            user_id=UUID(user_id),
        )

        # Get document details
        from app.core.database import get_supabase_client

        supabase = get_supabase_client()
        doc = (
            supabase.table("documents")
            .select("*")
            .eq("id", str(document_id))
            .single()
            .execute()
        )

        return DocumentResponse(
            id=str(document_id),
            filename=doc.data["filename"],  # type: ignore
            created_at=doc.data["created_at"],  # type: ignore
        )
    except Exception as e:
        logger.exception(
            "[DOC_UPLOAD] Failed to ingest document",
            extra={
                "doc_filename": file.filename,
                "doc_user_id": user_id,
                "doc_bytes": content_len,
            },
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    user_id: str = Depends(get_current_user_id),
):
    """List all documents for the current user."""
    from app.core.database import get_supabase_client

    supabase = get_supabase_client()
    result = (
        supabase.table("documents")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=str(doc.get("id", "")),  # type: ignore
                filename=str(doc.get("filename", "")),  # type: ignore
                created_at=str(doc.get("created_at", "")),  # type: ignore
            )
            for doc in (result.data or [])  # type: ignore
        ],
        total=len(result.data or []),  # type: ignore
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
