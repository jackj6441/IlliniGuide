from typing import Any, Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_name: str
    source_url: str
    course_id: str | None = None
    snippet: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    debug: bool = False


class DebugTrace(BaseModel):
    intent: str
    tool_calls: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    recommendation_scores: list[dict[str, Any]]


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    used_tools: list[str]
    debug_trace: DebugTrace | None
    latency_ms: int


class CompareRequest(BaseModel):
    course_ids: list[str] = Field(min_length=2)
    dimension: str | None = None
    debug: bool = False


class CourseSummary(BaseModel):
    course_id: str
    title: str
    notes: list[str]


class CompareResponse(BaseModel):
    summary: str
    courses: list[CourseSummary]
    comparison: dict[str, Any]
    citations: list[Citation]


class RecommendRequest(BaseModel):
    target_direction: str = Field(min_length=1)
    completed_courses: list[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=10)
    debug: bool = False


class Recommendation(BaseModel):
    course_id: str
    title: str
    reason: str
    citations: list[Citation]


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]
    debug_scores: list[dict[str, Any]] | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
