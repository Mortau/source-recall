from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from source_recall.config import Settings
from source_recall.indexing import IndexingError, RepositoryIndexer
from source_recall.repositories import RepositoryManager
from source_recall.state import StateStore


class FakeJetson:
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeQdrant:
    def __init__(self):
        self.existing = {"stale-point"}
        self.records = []
        self.deleted: set[str] = set()
        self.collection_ready = False

    def ensure_collection(self) -> None:
        self.collection_ready = True

    def repository_point_ids(self, repository: str) -> set[str]:
        assert repository == "example"
        return set(self.existing)

    def upsert(self, records, vectors) -> None:
        assert len(records) == len(vectors)
        self.records.extend(records)

    def delete_ids(self, point_ids: set[str]) -> int:
        self.deleted.update(point_ids)
        return len(point_ids)


def git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
    )


def committed_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "example"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.email", "tests@example.invalid")
    git(repository, "config", "user.name", "SourceRecall Tests")
    (repository / "app.py").write_text(
        "def greet():\n    return 'hello'\n", encoding="utf-8"
    )
    git(repository, "add", "app.py")
    git(repository, "commit", "-m", "initial")
    return repository


def build_indexer(tmp_path: Path):
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
    qdrant = FakeQdrant()
    indexer = RepositoryIndexer(
        settings,
        RepositoryManager(settings.repositories),
        state,
        qdrant,
        FakeJetson(),
    )
    return indexer, state, qdrant


def test_full_index_removes_stale_points_and_records_commit(tmp_path: Path) -> None:
    repository = committed_repository(tmp_path)
    indexer, state, qdrant = build_indexer(tmp_path)

    summary = indexer.index_repository("example")

    assert summary.files_indexed == 1
    assert summary.chunks_indexed == 1
    assert summary.stale_chunks_removed == 1
    assert qdrant.deleted == {"stale-point"}
    assert qdrant.records[0].path == "app.py"
    assert qdrant.records[0].index_generation
    assert (
        summary.indexed_commit
        == subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    metadata = state.get_repository_index("example")
    assert metadata is not None
    assert metadata["status"] == "ready"
    assert metadata["index_generation"] == qdrant.records[0].index_generation


def test_dirty_repository_is_rejected_and_recorded(tmp_path: Path) -> None:
    repository = committed_repository(tmp_path)
    indexer, state, _ = build_indexer(tmp_path)
    (repository / "app.py").write_text("changed\n", encoding="utf-8")

    with pytest.raises(IndexingError, match="uncommitted"):
        indexer.index_repository("example")

    metadata = state.get_repository_index("example")
    assert metadata is not None
    assert metadata["status"] == "failed"
