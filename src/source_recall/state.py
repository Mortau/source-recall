"""Durable SQLite state for indexing jobs and repository metadata."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIVE_JOB_STATES = ("queued", "processing")


class JobConflict(RuntimeError):
    """Raised when a repository already has an active indexing job."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, database_path: Path, history_limit: int = 100):
        self.database_path = database_path
        self.history_limit = history_limit

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    repository TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    files_seen INTEGER NOT NULL DEFAULT 0,
                    files_indexed INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    chunks_indexed INTEGER NOT NULL DEFAULT 0,
                    stale_chunks_removed INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS jobs_repository_status
                    ON jobs(repository, status);

                CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_active_per_repository
                    ON jobs(repository)
                    WHERE status IN ('queued', 'processing');

                CREATE TABLE IF NOT EXISTS repository_indexes (
                    repository TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    index_generation TEXT,
                    indexed_commit TEXT,
                    indexed_at TEXT,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    files_indexed INTEGER NOT NULL DEFAULT 0,
                    files_skipped INTEGER NOT NULL DEFAULT 0,
                    chunks_indexed INTEGER NOT NULL DEFAULT 0,
                    embedding_model TEXT NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL,
                    chunker_version TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    error TEXT
                );
                """
            )

    def recover_interrupted_jobs(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', completed_at = ?,
                    error = 'SourceRecall restarted before the job completed'
                WHERE status IN ('queued', 'processing')
                """,
                (utc_now(),),
            )
            return cursor.rowcount

    def create_job(self, job_id: str, repository: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO jobs(job_id, repository, status, created_at)
                    VALUES (?, ?, 'queued', ?)
                    """,
                    (job_id, repository, utc_now()),
                )
        except sqlite3.IntegrityError as exc:
            with self._connect() as connection:
                existing = connection.execute(
                    """
                    SELECT job_id FROM jobs
                    WHERE repository = ? AND status IN ('queued', 'processing')
                    LIMIT 1
                    """,
                    (repository,),
                ).fetchone()
            if existing is not None:
                raise JobConflict(
                    f"Repository already has active job {existing['job_id']}"
                ) from exc
            raise

    def start_job(self, job_id: str, total_files: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'processing', started_at = ?, total_files = ?
                WHERE job_id = ?
                """,
                (utc_now(), total_files, job_id),
            )

    def update_progress(
        self,
        job_id: str,
        *,
        files_seen: int,
        files_indexed: int,
        files_skipped: int,
        chunks_indexed: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET files_seen = ?, files_indexed = ?, files_skipped = ?,
                    chunks_indexed = ?
                WHERE job_id = ?
                """,
                (
                    files_seen,
                    files_indexed,
                    files_skipped,
                    chunks_indexed,
                    job_id,
                ),
            )

    def complete_job(self, job_id: str, stale_chunks_removed: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'completed', completed_at = ?,
                    stale_chunks_removed = ?, error = NULL
                WHERE job_id = ?
                """,
                (utc_now(), stale_chunks_removed, job_id),
            )

    def fail_job(self, job_id: str, error: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', completed_at = ?, error = ?
                WHERE job_id = ?
                """,
                (utc_now(), error[:1_000], job_id),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.history_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_index_success(
        self,
        *,
        repository: str,
        index_generation: str,
        indexed_commit: str | None,
        total_files: int,
        files_indexed: int,
        files_skipped: int,
        chunks_indexed: int,
        embedding_model: str,
        embedding_dimensions: int,
        schema_version: int,
        chunker_version: str,
        collection: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_indexes(
                    repository, status, index_generation, indexed_commit, indexed_at,
                    total_files, files_indexed, files_skipped, chunks_indexed,
                    embedding_model, embedding_dimensions, schema_version,
                    chunker_version, collection, error
                ) VALUES (?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(repository) DO UPDATE SET
                    status = excluded.status,
                    index_generation = excluded.index_generation,
                    indexed_commit = excluded.indexed_commit,
                    indexed_at = excluded.indexed_at,
                    total_files = excluded.total_files,
                    files_indexed = excluded.files_indexed,
                    files_skipped = excluded.files_skipped,
                    chunks_indexed = excluded.chunks_indexed,
                    embedding_model = excluded.embedding_model,
                    embedding_dimensions = excluded.embedding_dimensions,
                    schema_version = excluded.schema_version,
                    chunker_version = excluded.chunker_version,
                    collection = excluded.collection,
                    error = NULL
                """,
                (
                    repository,
                    index_generation,
                    indexed_commit,
                    utc_now(),
                    total_files,
                    files_indexed,
                    files_skipped,
                    chunks_indexed,
                    embedding_model,
                    embedding_dimensions,
                    schema_version,
                    chunker_version,
                    collection,
                ),
            )

    def record_index_failure(
        self,
        *,
        repository: str,
        error: str,
        embedding_model: str,
        embedding_dimensions: int,
        schema_version: int,
        chunker_version: str,
        collection: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO repository_indexes(
                    repository, status, embedding_model,
                    embedding_dimensions, schema_version, chunker_version,
                    collection, error
                ) VALUES (?, 'failed', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository) DO UPDATE SET
                    error = excluded.error
                """,
                (
                    repository,
                    embedding_model,
                    embedding_dimensions,
                    schema_version,
                    chunker_version,
                    collection,
                    error[:1_000],
                ),
            )

    def get_repository_index(self, repository: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM repository_indexes WHERE repository = ?",
                (repository,),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_repository_indexes(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM repository_indexes ORDER BY repository"
            ).fetchall()
        return [dict(row) for row in rows]
