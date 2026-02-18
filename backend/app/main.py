from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize services on application startup."""
    logger.info("[STARTUP] Initializing Revera services...")

    logger.info("[STARTUP] Revera services initialized successfully")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Multi-Agent Research Tool with Hybrid RAG",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
