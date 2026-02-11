import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Enable verbose logging in debug mode
if settings.debug:
    logging.getLogger("app").setLevel(logging.DEBUG)
    logger.info("[DEBUG] Debug mode enabled - verbose logging active")


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

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "app": settings.app_name}


# Import and include routers
from app.api import chats, documents, history, research  # noqa: E402

app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(history.router, prefix="/api/research/history", tags=["history"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
