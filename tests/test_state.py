from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from source_recall.state import JobConflict, StateStore


def store(tmp_path: Path) -> StateStore:
    state = StateStore(tmp_path / "state.db", history_limit=10)
    state.initialize()
    return state


def test_jobs_persist_progress_and_completion(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.create_job("job-1", "example")
    state.start_job("job-1", 4)
    state.update_progress(
        "job-1",
        files_seen=3,
        files_indexed=2,
        files_skipped=1,
        chunks_indexed=7,
    )
    state.complete_job("job-1", 2)

    job = state.get_job("job-1")
    assert job is not None
    assert job["status"] == "completed"
    assert job["chunks_indexed"] == 7
    assert job["stale_chunks_removed"] == 2


def test_duplicate_active_repository_job_is_rejected(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.create_job("job-1", "example")

    with pytest.raises(JobConflict, match="job-1"):
        state.create_job("job-2", "example")


def test_concurrent_active_repository_jobs_are_constrained(tmp_path: Path) -> None:
    state = store(tmp_path)

    def create(job_id: str) -> str:
        try:
            state.create_job(job_id, "example")
            return "created"
        except JobConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, ("job-1", "job-2")))

    assert sorted(outcomes) == ["conflict", "created"]


def test_restart_marks_interrupted_jobs_failed(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.create_job("job-1", "example")

    assert state.recover_interrupted_jobs() == 1
    job = state.get_job("job-1")
    assert job is not None
    assert job["status"] == "failed"
    assert "restarted" in job["error"]


def test_failed_refresh_preserves_last_active_generation(tmp_path: Path) -> None:
    state = store(tmp_path)
    state.record_index_success(
        repository="example",
        index_generation="generation-1",
        indexed_commit="abc123",
        total_files=1,
        files_indexed=1,
        files_skipped=0,
        chunks_indexed=2,
        embedding_model="model",
        embedding_dimensions=3,
        schema_version=1,
        chunker_version="line-v1",
        collection="collection",
    )
    state.record_index_failure(
        repository="example",
        error="refresh failed",
        embedding_model="model",
        embedding_dimensions=3,
        schema_version=1,
        chunker_version="line-v1",
        collection="collection",
    )

    metadata = state.get_repository_index("example")
    assert metadata is not None
    assert metadata["status"] == "ready"
    assert metadata["index_generation"] == "generation-1"
    assert metadata["error"] == "refresh failed"
