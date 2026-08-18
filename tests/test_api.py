from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from source_recall.api import create_app
from source_recall.config import Settings
from source_recall.repositories import RepositoryManager
from source_recall.retrieval import IndexStateError


class FakeState:
    def list_repository_indexes(self):
        return [
            {
                "repository": "example",
                "status": "ready",
                "index_generation": "generation-1",
            }
        ]

    def list_jobs(self):
        return []

    def get_job(self, job_id: str):
        return None


class FakeJobs:
    def submit(self, repository: str) -> str:
        assert repository == "example"
        return "job-1"


class FakeRetrieval:
    async def search(self, query: str, repository: str, limit: int):
        return {
            "query": query,
            "repository": repository,
            "indexed_commit": "abc123",
            "freshness": "current",
            "reranked": True,
            "vector_candidates": 1,
            "lexical_candidates": 1,
            "duration_ms": 1.5,
            "results": [
                {
                    "repository": repository,
                    "path": "app.py",
                    "start_line": 1,
                    "end_line": 2,
                    "content": "def main():\n    pass",
                    "sources": ["lexical", "vector"],
                    "vector_score": 0.8,
                    "lexical_score": 1.0,
                    "rrf_score": 0.03,
                    "rerank_score": 0.9,
                    "indexed_commit": "abc123",
                    "file_checksum": "checksum",
                }
            ][:limit],
        }


class FakeStaleRetrieval:
    async def search(self, query: str, repository: str, limit: int):
        raise IndexStateError("Repository changed after indexing")


class FakeRuntime:
    def __init__(self, repositories: RepositoryManager, retrieval=None):
        self.repositories = repositories
        self.state = FakeState()
        self.jobs = FakeJobs()
        self.retrieval = retrieval or FakeRetrieval()

    def startup(self) -> int:
        return 0

    async def shutdown(self) -> None:
        return None

    async def readiness(self):
        return {"status": "ready", "dependencies": {}}

    def status(self):
        return {"service": "source-recall", "repositories": []}


def configured_app(
    tmp_path: Path,
    token: str | None = None,
    retrieval=None,
):
    repository = tmp_path / "example"
    repository.mkdir()
    (repository / "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
    settings = Settings.from_mapping(
        {
            "repositories": {"root": str(tmp_path)},
            "state": {"database_path": str(tmp_path / "state.db")},
            "logging": {"file": None},
            "security": {"api_token": token},
        }
    )
    runtime = FakeRuntime(RepositoryManager(settings.repositories), retrieval)
    return create_app(settings, runtime)


def test_health_is_public_but_status_requires_configured_token(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=configured_app(tmp_path, "secret-token"))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            assert (await client.get("/live")).status_code == 200
            assert (await client.get("/ready")).status_code == 200
            assert (await client.get("/status")).status_code == 401
            response = await client.get(
                "/status", headers={"Authorization": "Bearer secret-token"}
            )
            assert response.status_code == 200
            assert response.headers["X-Request-ID"]

    asyncio.run(scenario())


def test_search_returns_provenance_and_enforces_runtime_limit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=configured_app(tmp_path))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/search",
                json={
                    "repository": "example",
                    "query": "application entry point",
                    "limit": 8,
                },
            )
            assert response.status_code == 200
            assert response.json()["results"][0]["indexed_commit"] == "abc123"

            too_many = await client.post(
                "/search",
                json={
                    "repository": "example",
                    "query": "entry",
                    "limit": 21,
                },
            )
            assert too_many.status_code == 400

    asyncio.run(scenario())


def test_index_endpoint_returns_durable_job_identifier(tmp_path: Path) -> None:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(app=configured_app(tmp_path))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post("/index", json={"repository": "example"})

    response = asyncio.run(scenario())
    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "job_id": "job-1",
        "repository": "example",
    }


def test_search_returns_conflict_for_a_stale_index(tmp_path: Path) -> None:
    async def scenario() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=configured_app(tmp_path, retrieval=FakeStaleRetrieval())
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/search",
                json={"repository": "example", "query": "entry point"},
            )

    response = asyncio.run(scenario())
    assert response.status_code == 409
    assert response.json() == {"detail": "Repository changed after indexing"}
