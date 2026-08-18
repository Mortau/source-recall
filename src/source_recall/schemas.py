"""Public HTTP request and response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .repositories import RepositoryError, validate_repository_name


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=16_000)
    repository: str = Field(min_length=1, max_length=128)
    limit: int | None = Field(default=None, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query cannot be blank")
        return value

    @field_validator("repository")
    @classmethod
    def repository_must_be_safe(cls, value: str) -> str:
        try:
            return validate_repository_name(value)
        except RepositoryError as exc:
            raise ValueError(str(exc)) from exc


class IndexRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=128)

    @field_validator("repository")
    @classmethod
    def repository_must_be_safe(cls, value: str) -> str:
        try:
            return validate_repository_name(value)
        except RepositoryError as exc:
            raise ValueError(str(exc)) from exc


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class SearchHit(BaseModel):
    repository: str
    path: str
    start_line: int
    end_line: int
    content: str
    sources: list[str]
    vector_score: float | None
    lexical_score: float | None
    rrf_score: float
    rerank_score: float | None
    indexed_commit: str | None = None
    file_checksum: str | None = None


class SearchResponse(BaseModel):
    query: str
    repository: str
    indexed_commit: str
    freshness: Literal["current", "unverifiable_working_tree"]
    reranked: bool
    vector_candidates: int
    lexical_candidates: int
    duration_ms: float
    results: list[SearchHit]


class IndexAcceptedResponse(BaseModel):
    status: Literal["accepted"]
    job_id: str
    repository: str


class FileResponse(BaseModel):
    repository: str
    path: str
    content: str


class MessageResponse(BaseModel):
    detail: str


class GenericResponse(BaseModel):
    model_config = {"extra": "allow"}

    status: str | None = None
    data: dict[str, Any] | None = None
