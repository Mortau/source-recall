"""Internal domain models shared by indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChunkRecord:
    point_id: str
    index_generation: str
    repository: str
    path: str
    sequence: int
    start_line: int
    end_line: int
    content: str
    file_checksum: str
    content_checksum: str
    indexed_commit: str | None


@dataclass
class SearchCandidate:
    repository: str
    path: str
    start_line: int
    end_line: int
    content: str
    sources: set[str] = field(default_factory=set)
    vector_score: float | None = None
    lexical_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    match_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.repository}:{self.path}:{self.start_line}:{self.end_line}"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repository": self.repository,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "sources": sorted(self.sources),
            "vector_score": self.vector_score,
            "lexical_score": self.lexical_score,
            "rrf_score": round(self.rrf_score, 8),
            "rerank_score": self.rerank_score,
        }
        payload.update(self.metadata)
        return payload
