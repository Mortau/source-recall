"""Hybrid vector, lexical, fusion, and reranking orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from threading import Event, Timer
from typing import Any

from .config import Settings
from .indexing import IndexingError, git_metadata
from .jetson_client import JetsonClientError, JetsonNlpClient
from .models import SearchCandidate
from .qdrant_store import QdrantStore
from .repositories import RepositoryManager
from .state import StateStore

logger = logging.getLogger("source_recall.retrieval")

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOP_WORDS = {
    "and",
    "are",
    "does",
    "find",
    "for",
    "from",
    "how",
    "the",
    "this",
    "what",
    "where",
    "with",
    "work",
    "works",
}


class RetrievalError(RuntimeError):
    """Raised when local retrieval cannot execute safely."""


class IndexStateError(RetrievalError):
    """Raised when a repository does not have a searchable current index."""


def _query_pattern(query: str) -> str:
    tokens = [
        token for token in _TOKEN.findall(query) if token.lower() not in _STOP_WORDS
    ]
    unique = list(dict.fromkeys(token.lower() for token in tokens))
    if not unique:
        return re.escape(query.strip())
    return "|".join(re.escape(token) for token in unique[:12])


def _context(path: Path, line_number: int, radius: int) -> tuple[int, int, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    return start, end, "\n".join(lines[start - 1 : end])


def lexical_search(
    query: str,
    repository: str,
    repositories: RepositoryManager,
    settings: Settings,
) -> list[SearchCandidate]:
    root = repositories.resolve(repository)
    command = [
        "rg",
        "--json",
        "--line-number",
        "--ignore-case",
        "--hidden",
        "--max-columns",
        str(settings.repositories.max_file_bytes),
    ]
    for extension in sorted(settings.repositories.include_extensions):
        command.extend(["--glob", f"*{extension}"])
    for directory in sorted(settings.repositories.exclude_dirs):
        command.extend(["--glob", f"!{directory}/**"])
    command.extend(["-e", _query_pattern(query), "--", "."])

    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise RetrievalError("ripgrep is unavailable") from exc

    candidates: list[SearchCandidate] = []
    seen: set[tuple[str, int]] = set()
    timed_out = Event()

    def terminate_on_timeout() -> None:
        timed_out.set()
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    timer = Timer(
        settings.retrieval.lexical_timeout_seconds,
        terminate_on_timeout,
    )
    timer.daemon = True
    timer.start()
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            try:
                item = json.loads(raw_line)
                if item.get("type") != "match":
                    continue
                data = item["data"]
                relative = Path(data["path"]["text"])
                line_number = int(data["line_number"])
                relative_path = relative.as_posix().removeprefix("./")
                key = (relative_path, line_number)
                if key in seen:
                    continue
                seen.add(key)
                file_path = repositories.resolve_file(repository, relative_path)
                if file_path.stat().st_size > settings.repositories.max_file_bytes:
                    continue
                start, end, content = _context(
                    file_path,
                    line_number,
                    settings.retrieval.lexical_context_lines,
                )
                candidates.append(
                    SearchCandidate(
                        repository=repository,
                        path=relative_path,
                        start_line=start,
                        end_line=end,
                        content=content,
                        sources={"lexical"},
                        lexical_score=1.0 / (len(candidates) + 1),
                        match_line=line_number,
                    )
                )
                if len(candidates) >= settings.retrieval.lexical_candidates:
                    break
            except (
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
                OSError,
                UnicodeDecodeError,
            ):
                continue
    finally:
        timer.cancel()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        if process.stdout is not None:
            process.stdout.close()
    if timed_out.is_set():
        raise RetrievalError("ripgrep search timed out")
    if process.returncode not in {0, 1, -15}:
        raise RetrievalError("ripgrep search failed")
    return candidates


def reciprocal_rank_fusion(
    vector_hits: list[SearchCandidate],
    lexical_hits: list[SearchCandidate],
    k: int,
) -> list[SearchCandidate]:
    """Fuse line hits into containing vector chunks before applying RRF."""

    documents: dict[str, SearchCandidate] = {}
    for rank, candidate in enumerate(vector_hits, 1):
        candidate.rrf_score += 1.0 / (k + rank)
        documents[candidate.key] = candidate

    fused_lexical_keys: set[str] = set()
    for rank, lexical in enumerate(lexical_hits, 1):
        containing = next(
            (
                vector
                for vector in vector_hits
                if vector.path == lexical.path
                and lexical.match_line is not None
                and vector.start_line <= lexical.match_line <= vector.end_line
            ),
            None,
        )
        target = containing or documents.setdefault(lexical.key, lexical)
        target.sources.add("lexical")
        if target.lexical_score is None:
            target.lexical_score = lexical.lexical_score
        if target.key not in fused_lexical_keys:
            target.rrf_score += 1.0 / (k + rank)
            fused_lexical_keys.add(target.key)

    return sorted(
        documents.values(),
        key=lambda item: (
            item.rrf_score,
            item.vector_score if item.vector_score is not None else -1.0,
            item.path,
        ),
        reverse=True,
    )


class RetrievalService:
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

    async def search(
        self,
        query: str,
        repository: str,
        limit: int,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        root = self.repositories.resolve(repository)
        index_metadata = self.state.get_repository_index(repository)
        if not index_metadata or not index_metadata.get("index_generation"):
            raise IndexStateError("Repository has no completed SourceRecall index")
        try:
            current_commit, clean = await asyncio.to_thread(git_metadata, root, False)
        except IndexingError as exc:
            raise IndexStateError(
                "Repository state cannot be verified; re-indexing is required"
            ) from exc
        indexed_commit = str(index_metadata.get("indexed_commit") or "")
        if indexed_commit.startswith("working-tree:"):
            expected_commit = indexed_commit.removeprefix("working-tree:")
            freshness = "unverifiable_working_tree"
        else:
            expected_commit = indexed_commit
            freshness = "current"
            if not clean:
                raise IndexStateError(
                    "Repository changed after indexing; re-index before searching"
                )
        if not expected_commit or current_commit != expected_commit:
            raise IndexStateError(
                "Repository commit differs from the active index; re-index required"
            )
        vector = await self.jetson.embed_query(query)
        vector_task = asyncio.to_thread(
            self.qdrant.query,
            repository,
            index_metadata["index_generation"],
            vector,
            self.settings.retrieval.vector_candidates,
        )
        lexical_task = asyncio.to_thread(
            lexical_search,
            query,
            repository,
            self.repositories,
            self.settings,
        )
        vector_hits, lexical_hits = await asyncio.gather(vector_task, lexical_task)
        fused = reciprocal_rank_fusion(
            vector_hits,
            lexical_hits,
            self.settings.retrieval.rrf_k,
        )
        candidates = fused[: self.settings.retrieval.rerank_candidates]
        reranked = False
        if self.settings.jetson_nlp.rerank_enabled and candidates:
            try:
                ranking = await self.jetson.rerank(
                    query, [candidate.content for candidate in candidates]
                )
                for index, score in ranking:
                    candidates[index].rerank_score = score
                candidates = [candidates[index] for index, _ in ranking]
                reranked = True
            except JetsonClientError as exc:
                logger.warning(
                    "Reranking unavailable; returning fused results",
                    extra={
                        "event": "rerank_fallback",
                        "repository": repository,
                        "error_type": type(exc).__name__,
                    },
                )

        results = candidates[:limit]
        duration_ms = round((time.perf_counter() - started) * 1_000, 3)
        logger.info(
            "Search completed",
            extra={
                "event": "search_completed",
                "repository": repository,
                "query_characters": len(query),
                "vector_candidates": len(vector_hits),
                "lexical_candidates": len(lexical_hits),
                "returned": len(results),
                "reranked": reranked,
                "duration_ms": duration_ms,
            },
        )
        return {
            "query": query,
            "repository": repository,
            "indexed_commit": indexed_commit,
            "freshness": freshness,
            "reranked": reranked,
            "vector_candidates": len(vector_hits),
            "lexical_candidates": len(lexical_hits),
            "duration_ms": duration_ms,
            "results": [candidate.as_dict() for candidate in results],
        }
