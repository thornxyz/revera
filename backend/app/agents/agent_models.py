"""Type-safe Pydantic models for agent communication.

These models provide runtime validation and type safety for data passed
between agents in the research pipeline.
"""

from pydantic import BaseModel, Field
from typing import Literal


class InternalSource(BaseModel):
    """A source retrieved from the internal document store."""

    chunk_id: str
    document_id: str
    content: str
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class WebSource(BaseModel):
    """A source retrieved from web search."""

    url: str
    title: str
    content: str
    score: float = 0.0


class ImageSource(BaseModel):
    """An image source with description."""

    document_id: str
    filename: str
    storage_path: str
    description: str
    mime_type: str = "image/jpeg"


class RetrievalContext(BaseModel):
    """Context passed to synthesis agent containing retrieved sources."""

    internal_sources: list[InternalSource] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    memory_prompt: str | None = None


class SynthesisSection(BaseModel):
    """A section in a synthesis result."""

    title: str
    content: str


class SynthesisResult(BaseModel):
    """Result from the synthesis agent."""

    answer: str
    sources_used: list[int] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    sections: list[SynthesisSection] = Field(default_factory=list)
    reasoning: str | None = None
    source_map: dict = Field(default_factory=dict)


class VerifiedClaim(BaseModel):
    """A claim that was verified against sources."""

    claim: str
    source: int
    status: str


class UnsupportedClaim(BaseModel):
    """A claim that could not be verified."""

    claim: str
    reason: str


class VerificationResult(BaseModel):
    """Result from the critic/verification agent."""

    verification_status: Literal[
        "verified",
        "partially_verified",
        "unverified",
        "timeout",
        "error",
        "pending",
        "skipped",
    ]
    confidence_score: float = 0.0
    verified_claims: list[VerifiedClaim] = Field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = Field(default_factory=list)
    overall_assessment: str = ""
    criticism: str | None = None
    message: str | None = None  # For error/timeout cases


class ExecutionStep(BaseModel):
    """A step in the execution plan."""

    tool: Literal["rag", "web", "synthesis", "verification", "image_gen"] = "rag"
    description: str = ""
    parameters: dict = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """Plan created by the planner agent."""

    subtasks: list[str] = Field(default_factory=list)
    steps: list[ExecutionStep] = Field(default_factory=list)
    approach: str = ""
    constraints: dict = Field(default_factory=dict)


class NormalizedSource(BaseModel):
    """A normalized source for API responses."""

    type: Literal["internal", "web", "image"]
    content: str
    score: float = 0.0
    # Internal-specific
    chunk_id: str | None = None
    document_id: str | None = None
    # Web-specific
    url: str | None = None
    title: str | None = None
    # Image-specific
    filename: str | None = None
    storage_path: str | None = None
