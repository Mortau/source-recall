"""Authoritative repository indexing into Qdrant."""

from __future__ import annotations

import hashlib
import logging
import subprocess
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .chunking import chunk_text
from .config import Settings
from .jetson_client import JetsonNlpClient
from .models import ChunkRecord
from .qdrant_store import QdrantStore
from .repositories import RepositoryManager
from .state import StateStore

logger = logging.getLogger("source_recall.indexing")


class IndexingError(RuntimeError):
    """Raised when repository state cannot be indexed reliably."""


@dataclass(frozen=True)
class IndexSummary:
    repository: str
    indexed_commit: str | None
    total_files: int
    files_indexed: int
    files_skipped: int
    chunks_indexed: int
    stale_chunks_removed: int


def _git(root: Path, *arguments: str, timeout: float = 30.0) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IndexingError("Unable to execute Git for repository indexing") from exc
    if result.returncode != 0:
        raise IndexingError("Repository is not a readable Git working tree")
    return result.stdout


def git_metadata(root: Path, require_clean: bool) -> tuple[str, bool]:
    commit = _git(root, "rev-parse", "HEAD").decode("ascii", errors="strict").strip()
    status = _git(root, "status", "--porcelain", "--untracked-files=normal")
    clean = not status.strip()
    if require_clean and not clean:
        raise IndexingError(
            "Repository has uncommitted changes; commit or clean it before indexing"
        )
    return commit, clean


class RepositoryIndexer:
    def __init__(
        self,
        settings: Settings,
        repositories: RepositoryManager,
        state: StateStore,
        qdrant: QdrantStore,
        jetson: JetsonNlpClient,
    ):
        self.settings = settings
        self.repositories = repositories
        self.state = state
        self.qdrant = qdrant
        self.jetson = jetson

    def _eligible(self, root: Path, path: Path) -> bool:
        try:
            relative = path.relative_to(root)
            resolved = path.resolve()
        except (OSError, ValueError):
            return False
        return (
            path.is_file()
            and resolved.is_relative_to(root)
            and path.suffix.lower() in self.settings.repositories.include_extensions
            and not any(
                part in self.settings.repositories.exclude_dirs
                for part in relative.parts
            )
        )

    def discover_files(self, root: Path) -> list[Path]:
        arguments = ["ls-files", "-z", "--cached"]
        if not self.settings.repositories.git_tracked_only:
            arguments.extend(["--others", "--exclude-standard"])
        raw_paths = _git(root, *arguments)
        discovered: list[Path] = []
        for raw_path in raw_paths.split(b"\0"):
            if not raw_path:
                continue
            try:
                relative = Path(raw_path.decode("utf-8", errors="strict"))
            except UnicodeDecodeError:
                continue
            path = root / relative
            if self._eligible(root, path):
                discovered.append(path)
        return sorted(discovered, key=lambda item: item.as_posix().casefold())

    def _read_file(self, path: Path) -> str | None:
        try:
            if path.stat().st_size > self.settings.repositories.max_file_bytes:
                return None
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _record(
        self,
        *,
        repository: str,
        index_generation: str,
        relative_path: str,
        sequence: int,
        start_line: int,
        end_line: int,
        content: str,
        file_checksum: str,
        indexed_commit: str | None,
    ) -> ChunkRecord:
        seed = (
            f"{repository}:{index_generation}:{relative_path}:{sequence}:"
            f"{start_line}:{end_line}:"
            f"{self.settings.indexing.chunker_version}"
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
        return ChunkRecord(
            point_id=str(uuid.UUID(digest)),
            index_generation=index_generation,
            repository=repository,
            path=relative_path,
            sequence=sequence,
            start_line=start_line,
            end_line=end_line,
            content=content,
            file_checksum=file_checksum,
            content_checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            indexed_commit=indexed_commit,
        )

    def _flush(
        self,
        records: list[ChunkRecord],
        current_ids: set[str],
    ) -> int:
        if not records:
            return 0
        vectors = self.jetson.embed_batch([record.content for record in records])
        self.qdrant.upsert(records, vectors)
        current_ids.update(record.point_id for record in records)
        count = len(records)
        records.clear()
        return count

    def index_repository(
        self,
        repository: str,
        job_id: str | None = None,
    ) -> IndexSummary:
        root = self.repositories.resolve(repository)
        indexed_commit: str | None = None
        files_indexed = 0
        files_skipped = 0
        chunks_indexed = 0
        files_seen = 0
        index_generation = uuid.uuid4().hex
        try:
            indexed_commit, clean = git_metadata(
                root, self.settings.repositories.require_clean_git
            )
            if not clean:
                indexed_commit = f"working-tree:{indexed_commit}"
            files = self.discover_files(root)
            if job_id:
                self.state.start_job(job_id, len(files))

            self.qdrant.ensure_collection()
            existing_ids = self.qdrant.repository_point_ids(repository)
            current_ids: set[str] = set()
            pending: list[ChunkRecord] = []

            for path in files:
                files_seen += 1
                text = self._read_file(path)
                if text is None:
                    files_skipped += 1
                    continue
                chunks = chunk_text(
                    text,
                    self.settings.indexing.chunk_max_characters,
                    self.settings.indexing.chunk_overlap_lines,
                )
                if not chunks:
                    files_skipped += 1
                    continue
                files_indexed += 1
                relative_path = path.relative_to(root).as_posix()
                file_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
                for chunk in chunks:
                    pending.append(
                        self._record(
                            repository=repository,
                            index_generation=index_generation,
                            relative_path=relative_path,
                            sequence=chunk.sequence,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            content=chunk.content,
                            file_checksum=file_checksum,
                            indexed_commit=indexed_commit,
                        )
                    )
                    if len(pending) >= self.settings.indexing.batch_size:
                        chunks_indexed += self._flush(pending, current_ids)

                if job_id:
                    self.state.update_progress(
                        job_id,
                        files_seen=files_seen,
                        files_indexed=files_indexed,
                        files_skipped=files_skipped,
                        chunks_indexed=chunks_indexed,
                    )

            chunks_indexed += self._flush(pending, current_ids)
            self.state.record_index_success(
                repository=repository,
                index_generation=index_generation,
                indexed_commit=indexed_commit,
                total_files=len(files),
                files_indexed=files_indexed,
                files_skipped=files_skipped,
                chunks_indexed=chunks_indexed,
                embedding_model=self.settings.jetson_nlp.embedding_model,
                embedding_dimensions=self.settings.qdrant.embedding_dimensions,
                schema_version=self.settings.indexing.schema_version,
                chunker_version=self.settings.indexing.chunker_version,
                collection=self.settings.qdrant.collection,
            )
            try:
                stale_removed = self.qdrant.delete_ids(existing_ids - current_ids)
            except Exception as exc:
                stale_removed = 0
                logger.warning(
                    "New index activated but stale-point cleanup failed",
                    extra={
                        "event": "stale_cleanup_failed",
                        "repository": repository,
                        "error_type": type(exc).__name__,
                    },
                )
            if job_id:
                self.state.update_progress(
                    job_id,
                    files_seen=files_seen,
                    files_indexed=files_indexed,
                    files_skipped=files_skipped,
                    chunks_indexed=chunks_indexed,
                )
                self.state.complete_job(job_id, stale_removed)
            summary = IndexSummary(
                repository=repository,
                indexed_commit=indexed_commit,
                total_files=len(files),
                files_indexed=files_indexed,
                files_skipped=files_skipped,
                chunks_indexed=chunks_indexed,
                stale_chunks_removed=stale_removed,
            )
            logger.info(
                "Repository indexing completed",
                extra={"event": "index_completed", **summary.__dict__},
            )
            return summary
        except Exception as exc:
            if job_id:
                self.state.fail_job(job_id, str(exc))
            self.state.record_index_failure(
                repository=repository,
                error=str(exc),
                embedding_model=self.settings.jetson_nlp.embedding_model,
                embedding_dimensions=self.settings.qdrant.embedding_dimensions,
                schema_version=self.settings.indexing.schema_version,
                chunker_version=self.settings.indexing.chunker_version,
                collection=self.settings.qdrant.collection,
            )
            logger.exception(
                "Repository indexing failed",
                extra={"event": "index_failed", "repository": repository},
            )
            raise


def batched(values: Iterable[ChunkRecord], size: int) -> Iterable[list[ChunkRecord]]:
    """Yield bounded batches; retained for reuse by incremental indexing."""

    batch: list[ChunkRecord] = []
    for value in values:
        batch.append(value)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
