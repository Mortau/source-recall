"""Composition root for SourceRecall services and lifecycle."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from .config import Settings
from .indexing import RepositoryIndexer
from .jetson_client import JetsonNlpClient
from .jobs import JobManager
from .qdrant_store import QdrantStore
from .repositories import RepositoryManager
from .retrieval import RetrievalService
from .state import StateStore


class SourceRecallRuntime:
    def __init__(
        self,
        settings: Settings,
        *,
        repositories: RepositoryManager | None = None,
        state: StateStore | None = None,
        qdrant: QdrantStore | None = None,
        jetson: JetsonNlpClient | None = None,
    ):
        self.settings = settings
        self.repositories = repositories or RepositoryManager(settings.repositories)
        self.state = state or StateStore(
            settings.state.database_path,
            settings.state.job_history_limit,
        )
        self.qdrant = qdrant or QdrantStore(
            settings.qdrant, settings.jetson_nlp, settings.indexing
        )
        self.jetson = jetson or JetsonNlpClient(settings.jetson_nlp, settings.qdrant)
        self.indexer = RepositoryIndexer(
            settings,
            self.repositories,
            self.state,
            self.qdrant,
            self.jetson,
        )
        self.jobs = JobManager(self.state, self.indexer)
        self.retrieval = RetrievalService(
            settings,
            self.repositories,
            self.state,
            self.qdrant,
            self.jetson,
        )

    def startup(self) -> int:
        self.state.initialize()
        return self.state.recover_interrupted_jobs()

    async def shutdown(self) -> None:
        self.jobs.shutdown()
        self.qdrant.close()
        await self.jetson.close()

    async def readiness(self) -> dict[str, Any]:
        dependencies: dict[str, Any] = {
            "qdrant": {"status": "unknown"},
            "jetson_nlp": {"status": "unknown"},
            "ripgrep": {"status": "ok" if shutil.which("rg") else "unavailable"},
        }
        try:
            await asyncio.to_thread(self.qdrant.health)
            dependencies["qdrant"]["status"] = "ok"
        except Exception:
            dependencies["qdrant"]["status"] = "unavailable"
        try:
            details = await self.jetson.readiness()
            dependencies["jetson_nlp"] = {"status": "ok", "details": details}
        except Exception:
            dependencies["jetson_nlp"]["status"] = "unavailable"
        ready = all(
            dependency["status"] == "ok" for dependency in dependencies.values()
        )
        return {
            "status": "ready" if ready else "not_ready",
            "dependencies": dependencies,
        }

    def status(self) -> dict[str, Any]:
        return {
            "service": "source-recall",
            "collection": self.settings.qdrant.collection,
            "embedding_model": self.settings.jetson_nlp.embedding_model,
            "embedding_dimensions": self.settings.qdrant.embedding_dimensions,
            "schema_version": self.settings.indexing.schema_version,
            "chunker_version": self.settings.indexing.chunker_version,
            "repository_root": str(self.settings.repositories.root),
            "repositories": self.state.list_repository_indexes(),
        }
