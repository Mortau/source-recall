from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from source_recall.config import Settings
from source_recall.models import SearchCandidate
from source_recall.repositories import RepositoryManager
from source_recall.retrieval import (
    RetrievalError,
    RetrievalService,
    _query_pattern,
    reciprocal_rank_fusion,
)
from source_recall.state import StateStore


def candidate(
    source: str,
    path: str,
    start: int,
    end: int,
    match_line: int | None = None,
) -> SearchCandidate:
    return SearchCandidate(
        repository="example",
        path=path,
        start_line=start,
        end_line=end,
        content="source",
        sources={source},
        vector_score=0.8 if source == "vector" else None,
        lexical_score=1.0 if source == "lexical" else None,
        match_line=match_line,
    )


def test_query_pattern_removes_generic_words() -> None:
    assert _query_pattern("how does authentication middleware work") == (
        "authentication|middleware"
    )


def test_lexical_line_fuses_into_containing_vector_chunk() -> None:
    vector = candidate("vector", "app.py", 10, 30)
    lexical = candidate("lexical", "app.py", 15, 25, match_line=20)

    results = reciprocal_rank_fusion([vector], [lexical], 60)

    assert len(results) == 1
    assert results[0].sources == {"vector", "lexical"}
    assert results[0].rrf_score == pytest.approx(2 / 61)


def test_non_overlapping_lexical_hit_remains_a_candidate() -> None:
    vector = candidate("vector", "app.py", 1, 10)
    lexical = candidate("lexical", "other.py", 20, 30, match_line=25)

    results = reciprocal_rank_fusion([vector], [lexical], 60)

    assert len(results) == 2


class FakeJetson:
    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def rerank(self, query: str, documents: list[str]):
        return []


class FakeQdrant:
    def query(
        self,
        repository: str,
        index_generation: str,
        vector: list[float],
        limit: int,
    ) -> list[SearchCandidate]:
        return []


def test_search_rejects_working_tree_drift(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "example"
    repository.mkdir()
    subprocess.run(["git", "-C", str(repository), "init"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Tests"],
        check=True,
    )
    source = repository / "app.py"
    source.write_text("print('ready')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "app.py"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "initial"], check=True
    )
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    settings = Settings.from_mapping(
        {
            "repositories": {"root": str(tmp_path)},
            "qdrant": {"embedding_dimensions": 3},
            "state": {"database_path": str(tmp_path / "state.db")},
            "logging": {"file": None},
        }
    )
    state = StateStore(settings.state.database_path)
    state.initialize()
    state.record_index_success(
        repository="example",
        index_generation="generation-1",
        indexed_commit=commit,
        total_files=1,
        files_indexed=1,
        files_skipped=0,
        chunks_indexed=1,
        embedding_model=settings.jetson_nlp.embedding_model,
        embedding_dimensions=3,
        schema_version=1,
        chunker_version="line-v1",
        collection=settings.qdrant.collection,
    )
    monkeypatch.setattr("source_recall.retrieval.lexical_search", lambda *args: [])
    service = RetrievalService(
        settings,
        RepositoryManager(settings.repositories),
        state,
        FakeQdrant(),
        FakeJetson(),
    )

    result = asyncio.run(service.search("entry point", "example", 8))
    assert result["freshness"] == "current"

    source.write_text("print('changed')\n", encoding="utf-8")
    with pytest.raises(RetrievalError, match="changed after indexing"):
        asyncio.run(service.search("entry point", "example", 8))
