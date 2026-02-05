"""Pydantic models for database entities."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    """Base document model."""

    filename: str
    metadata: dict = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    """Model for creating a document."""

    pass


class Document(DocumentBase):
    """Full document model with all fields."""

    id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentChunkBase(BaseModel):
    """Base chunk model."""

    content: str
    metadata: dict = Field(default_factory=dict)


class DocumentChunk(DocumentChunkBase):
    """Full chunk model with embedding."""

    id: UUID
    document_id: UUID
    embedding: list[float] | None = None

    class Config:
        from_attributes = True


class ResearchSessionBase(BaseModel):
    """Base research session model."""

    query: str


class ResearchSessionCreate(ResearchSessionBase):
    """Model for creating a research session."""

    pass


class ResearchSession(ResearchSessionBase):
    """Full research session model."""

    id: UUID
    user_id: UUID
    created_at: datetime
    status: str = "pending"  # pending, running, completed, failed

    class Config:
        from_attributes = True


class AgentLogBase(BaseModel):
    """Base agent log model."""

    agent_name: str
    events: dict = Field(default_factory=dict)


class AgentLog(AgentLogBase):
    """Full agent log model."""

    id: UUID
    session_id: UUID
    created_at: datetime
    latency_ms: int | None = None

    class Config:
        from_attributes = True


# ============================================
# Chat Models (Multi-Turn Conversations)
# ============================================


class ChatBase(BaseModel):
    """Base chat model."""

    title: str | None = None


class ChatCreate(ChatBase):
    """Model for creating a chat."""

    pass


class Chat(ChatBase):
    """Full chat model."""

    id: UUID
    user_id: UUID
    thread_id: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatWithPreview(Chat):
    """Chat with message preview for list views."""

    last_message_preview: str | None = None
    message_count: int = 0


# ============================================
# Message Models
# ============================================


class MessageBase(BaseModel):
    """Base message model."""

    query: str


class MessageCreate(MessageBase):
    """Model for creating a message."""

    pass


class Message(MessageBase):
    """Full message model."""

    id: UUID
    chat_id: UUID
    session_id: UUID | None
    query: str
    answer: str | None
    role: str  # 'user' or 'assistant'
    sources: list[dict] = Field(default_factory=list)
    verification: dict | None = None
    confidence: str | None = None
    thinking: str | None = None
    agent_timeline: list[dict] | None = None
    created_at: datetime

    class Config:
        from_attributes = True
