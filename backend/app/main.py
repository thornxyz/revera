import contextvars
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging_config import setup_logging, get_logger

# Setup logging before any other imports
settings = get_settings()
setup_logging(level=settings.log_level, log_format=settings.log_format)

logger = get_logger(__name__)

# Enable verbose logging in debug mode
if settings.debug:
    import logging

    logging.getLogger("app").setLevel(logging.DEBUG)
    logger.info("[DEBUG] Debug mode enabled - verbose logging active")

# Rate limiter - 60 requests per minute by default
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# Context variable for per-request ID (injected by RequestIdMiddleware)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a UUID request_id to every request and response."""

    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        request_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


# Maximum allowed body size (10 MB) — rejects oversized non-upload requests early.
MAX_BODY_SIZE = 10 * 1024 * 1024


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject non-upload requests whose body exceeds MAX_BODY_SIZE."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        # Skip multipart uploads — file-upload handlers enforce their own limits.
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type and content_length is not None:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
        return await call_next(request)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    if isinstance(exc, RateLimitExceeded):
        detail = f"Rate limit exceeded: {exc.detail}"
    else:
        detail = "Rate limit exceeded"
    return JSONResponse(
        status_code=429,
        content={"detail": detail},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize services on application startup."""
    logger.info("[STARTUP] Initializing Revera services...")

    # Initialize LangGraph checkpointer (creates pool + tables if DB URL set)
    from app.core.checkpointer import get_checkpointer, close_checkpointer

    checkpointer = await get_checkpointer()
    if checkpointer:
        logger.info("[STARTUP] LangGraph checkpointer ready")
    else:
        logger.warning("[STARTUP] LangGraph checkpointer not available")

    logger.info("[STARTUP] Revera services initialized successfully")
    yield

    # Shutdown: close checkpointer connection pool
    logger.info("[SHUTDOWN] Closing Revera services...")
    await close_checkpointer()
    logger.info("[SHUTDOWN] Revera services closed")


app = FastAPI(
    title=settings.app_name,
    description="Multi-Agent Research Tool with Hybrid RAG",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Per-request ID and body-size guard (added before CORS so headers are set early)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestIdMiddleware)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.get("/health")
@limiter.exempt
async def health_check(request: Request):
    """Health check endpoint (rate limit exempt)."""
    return {"status": "healthy", "app": settings.app_name}


# Import and include routers
from app.api import chats, documents, history, research  # noqa: E402

app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(history.router, prefix="/api/research/history", tags=["history"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
