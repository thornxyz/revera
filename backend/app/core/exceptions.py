"""Custom exception hierarchy for Revera application.

Provides structured error handling with:
- Error codes for machine-readable identification
- Recovery hints for graceful degradation
- HTTP status codes for API responses
- Context preservation for debugging
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ErrorCodes:
    """Central registry of error codes."""

    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"

    GEMINI_TIMEOUT = "GEMINI_TIMEOUT"
    GEMINI_RATE_LIMITED = "GEMINI_RATE_LIMITED"
    GEMINI_API_ERROR = "GEMINI_API_ERROR"
    GEMINI_INVALID_RESPONSE = "GEMINI_INVALID_RESPONSE"

    QDRANT_CONNECTION_ERROR = "QDRANT_CONNECTION_ERROR"
    QDRANT_QUERY_ERROR = "QDRANT_QUERY_ERROR"
    QDRANT_UPSERT_ERROR = "QDRANT_UPSERT_ERROR"

    TAVILY_ERROR = "TAVILY_ERROR"
    TAVILY_RATE_LIMITED = "TAVILY_RATE_LIMITED"

    SUPABASE_ERROR = "SUPABASE_ERROR"

    INGESTION_ERROR = "INGESTION_ERROR"
    INGESTION_PDF_ERROR = "INGESTION_PDF_ERROR"
    INGESTION_IMAGE_ERROR = "INGESTION_IMAGE_ERROR"
    INGESTION_EMBEDDING_ERROR = "INGESTION_EMBEDDING_ERROR"

    RESEARCH_ERROR = "RESEARCH_ERROR"
    PLANNING_ERROR = "PLANNING_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    SYNTHESIS_ERROR = "SYNTHESIS_ERROR"
    CRITIC_ERROR = "CRITIC_ERROR"
    IMAGE_GEN_ERROR = "IMAGE_GEN_ERROR"

    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class ReveraError(Exception):
    """Base exception for all Revera errors.

    Attributes:
        error_code: Machine-readable error code from ErrorCodes
        message: Human-readable error message
        details: Additional context (user_id, chat_id, etc.)
        recoverable: Whether retry might help
        http_status: HTTP status code for API responses
        suggested_action: Hint for what to do next
        retry_after: Seconds to wait before retry (if applicable)
    """

    error_code: str = ErrorCodes.INTERNAL_ERROR
    message: str = "An unexpected error occurred"
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = False
    http_status: int = 500
    suggested_action: str | None = None
    retry_after: int | None = None

    def __post_init__(self):
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "error_code": self.error_code,
            "message": self.message,
            "recoverable": self.recoverable,
        }
        if self.suggested_action:
            result["suggested_action"] = self.suggested_action
        if self.retry_after:
            result["retry_after"] = self.retry_after
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class ConfigurationError(ReveraError):
    """Application configuration error (missing env vars, invalid config)."""

    error_code: str = ErrorCodes.CONFIGURATION_ERROR
    message: str = "Configuration error"
    http_status: int = 500
    recoverable: bool = False


@dataclass
class AuthenticationError(ReveraError):
    """Authentication failure (invalid JWT, user not found)."""

    error_code: str = ErrorCodes.AUTHENTICATION_ERROR
    message: str = "Authentication failed"
    http_status: int = 401
    recoverable: bool = False


@dataclass
class AuthorizationError(ReveraError):
    """Authorization failure (user lacks permission)."""

    error_code: str = ErrorCodes.AUTHORIZATION_ERROR
    message: str = "Access denied"
    http_status: int = 403
    recoverable: bool = False


@dataclass
class ValidationError(ReveraError):
    """Input validation failure."""

    error_code: str = ErrorCodes.VALIDATION_ERROR
    message: str = "Validation error"
    http_status: int = 400
    recoverable: bool = False


@dataclass
class RateLimitError(ReveraError):
    """Rate limiting exceeded."""

    error_code: str = ErrorCodes.RATE_LIMIT_ERROR
    message: str = "Rate limit exceeded"
    http_status: int = 429
    recoverable: bool = True
    suggested_action: str = "Please wait before retrying"


@dataclass
class ExternalServiceError(ReveraError):
    """Base for external service errors."""

    service_name: str = "unknown"
    http_status: int = 502
    recoverable: bool = True


@dataclass
class GeminiError(ExternalServiceError):
    """Google Gemini API errors."""

    error_code: str = ErrorCodes.GEMINI_API_ERROR
    message: str = "Gemini API error"
    service_name: str = "gemini"
    suggested_action: str = "Please try again in a moment"


@dataclass
class GeminiTimeoutError(GeminiError):
    """Gemini request timed out."""

    error_code: str = ErrorCodes.GEMINI_TIMEOUT
    message: str = "LLM request timed out"
    recoverable: bool = True
    suggested_action: str = "Request took too long. Please try with a shorter query"


@dataclass
class GeminiRateLimitError(GeminiError):
    """Gemini rate limit exceeded."""

    error_code: str = ErrorCodes.GEMINI_RATE_LIMITED
    message: str = "AI service rate limit exceeded"
    http_status: int = 429
    recoverable: bool = True
    suggested_action: str = "Please wait a moment before retrying"


@dataclass
class GeminiInvalidResponseError(GeminiError):
    """Gemini returned invalid/unparseable response."""

    error_code: str = ErrorCodes.GEMINI_INVALID_RESPONSE
    message: str = "Invalid response from AI service"
    recoverable: bool = True


@dataclass
class QdrantError(ExternalServiceError):
    """Qdrant vector database errors."""

    error_code: str = ErrorCodes.QDRANT_CONNECTION_ERROR
    message: str = "Vector database error"
    service_name: str = "qdrant"
    suggested_action: str = "Search temporarily unavailable. Please try again"


@dataclass
class QdrantConnectionError(QdrantError):
    """Cannot connect to Qdrant."""

    error_code: str = ErrorCodes.QDRANT_CONNECTION_ERROR
    message: str = "Cannot connect to vector database"
    recoverable: bool = True


@dataclass
class QdrantQueryError(QdrantError):
    """Query execution failed in Qdrant."""

    error_code: str = ErrorCodes.QDRANT_QUERY_ERROR
    message: str = "Vector search failed"
    recoverable: bool = True


@dataclass
class QdrantUpsertError(QdrantError):
    """Upsert operation failed in Qdrant."""

    error_code: str = ErrorCodes.QDRANT_UPSERT_ERROR
    message: str = "Failed to store embeddings"
    recoverable: bool = True


@dataclass
class TavilyError(ExternalServiceError):
    """Tavily web search errors."""

    error_code: str = ErrorCodes.TAVILY_ERROR
    message: str = "Web search error"
    service_name: str = "tavily"
    suggested_action: str = "Web search temporarily unavailable"


@dataclass
class TavilyRateLimitError(TavilyError):
    """Tavily rate limit exceeded."""

    error_code: str = ErrorCodes.TAVILY_RATE_LIMITED
    message: str = "Web search rate limit exceeded"
    http_status: int = 429
    recoverable: bool = True


@dataclass
class SupabaseError(ExternalServiceError):
    """Supabase database errors."""

    error_code: str = ErrorCodes.SUPABASE_ERROR
    message: str = "Database error"
    service_name: str = "supabase"
    suggested_action: str = "Database temporarily unavailable. Please try again"


@dataclass
class IngestionError(ReveraError):
    """Document ingestion errors."""

    error_code: str = ErrorCodes.INGESTION_ERROR
    message: str = "Document processing failed"
    http_status: int = 500
    recoverable: bool = False


@dataclass
class IngestionPdfError(IngestionError):
    """PDF processing failed."""

    error_code: str = ErrorCodes.INGESTION_PDF_ERROR
    message: str = "Failed to process PDF file"


@dataclass
class IngestionImageError(IngestionError):
    """Image processing failed."""

    error_code: str = ErrorCodes.INGESTION_IMAGE_ERROR
    message: str = "Failed to process image file"


@dataclass
class IngestionEmbeddingError(IngestionError):
    """Embedding generation failed during ingestion."""

    error_code: str = ErrorCodes.INGESTION_EMBEDDING_ERROR
    message: str = "Failed to generate embeddings"
    recoverable: bool = True


@dataclass
class ResearchError(ReveraError):
    """Research workflow errors."""

    error_code: str = ErrorCodes.RESEARCH_ERROR
    message: str = "Research workflow failed"
    http_status: int = 500
    recoverable: bool = True


@dataclass
class PlanningError(ResearchError):
    """Planning agent failed."""

    error_code: str = ErrorCodes.PLANNING_ERROR
    message: str = "Failed to analyze query"


@dataclass
class RetrievalError(ResearchError):
    """Retrieval agent failed."""

    error_code: str = ErrorCodes.RETRIEVAL_ERROR
    message: str = "Failed to retrieve documents"


@dataclass
class SynthesisError(ResearchError):
    """Synthesis agent failed."""

    error_code: str = ErrorCodes.SYNTHESIS_ERROR
    message: str = "Failed to generate answer"


@dataclass
class CriticError(ResearchError):
    """Critic agent failed."""

    error_code: str = ErrorCodes.CRITIC_ERROR
    message: str = "Failed to verify answer"


@dataclass
class ImageGenError(ResearchError):
    """Image generation failed."""

    error_code: str = ErrorCodes.IMAGE_GEN_ERROR
    message: str = "Failed to generate image"
