"""FastAPI composition and HTTP routes for SourceRecall."""

from __future__ import annotations

import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status

from . import __version__
from .config import Settings
from .jetson_client import JetsonClientError
from .logging_config import configure_logging, reset_request_id, set_request_id
from .qdrant_store import QdrantContractError, QdrantOperationError
from .repositories import RepositoryError
from .retrieval import IndexStateError, RetrievalError
from .runtime import SourceRecallRuntime
from .schemas import (
    FileResponse,
    IndexAcceptedResponse,
    IndexRequest,
    LivenessResponse,
    SearchRequest,
    SearchResponse,
)
from .state import JobConflict

logger = logging.getLogger("source_recall.api")
_PUBLIC_PATHS = {"/live", "/ready", "/health", "/docs", "/openapi.json"}


def _request_id(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "").strip()
    if candidate and len(candidate) <= 128 and candidate.isprintable():
        return candidate
    return uuid.uuid4().hex


def _authorized(request: Request, expected_token: str | None) -> bool:
    if expected_token is None or request.url.path in _PUBLIC_PATHS:
        return True
    authorization = request.headers.get("Authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(supplied, expected_token)


def create_app(
    settings: Settings | None = None,
    runtime: SourceRecallRuntime | None = None,
) -> FastAPI:
    active_settings = settings or Settings.load()
    configure_logging(active_settings.logging)
    active_runtime = runtime or SourceRecallRuntime(active_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        recovered = active_runtime.startup()
        logger.info(
            "SourceRecall started",
            extra={
                "event": "service_started",
                "recovered_jobs": recovered,
                "version": __version__,
            },
        )
        try:
            yield
        finally:
            await active_runtime.shutdown()
            logger.info("SourceRecall stopped", extra={"event": "service_stopped"})

    application = FastAPI(
        title="SourceRecall API",
        version=__version__,
        description="Self-hosted repository indexing and hybrid code retrieval.",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.runtime = active_runtime

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = _request_id(request)
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            if not _authorized(request, active_settings.security.api_token):
                response = Response(
                    content='{"detail":"Unauthorized"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "Unhandled request failure",
                extra={
                    "event": "http_request_unhandled_error",
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        finally:
            logger.info(
                "Request completed",
                extra={
                    "event": "http_request_completed",
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1_000, 3),
                },
            )
            reset_request_id(token)

    @application.get("/live", response_model=LivenessResponse)
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/health")
    @application.get("/ready")
    async def ready(response: Response) -> dict[str, Any]:
        payload = await active_runtime.readiness()
        response.status_code = (
            status.HTTP_200_OK
            if payload["status"] == "ready"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return payload

    @application.get("/status")
    def service_status() -> dict[str, Any]:
        return active_runtime.status()

    @application.get("/repositories")
    def list_repositories() -> dict[str, Any]:
        indexed = {
            item["repository"]: item
            for item in active_runtime.state.list_repository_indexes()
        }
        return {
            "repositories": [
                {
                    "repository": name,
                    "index": indexed.get(name),
                }
                for name in active_runtime.repositories.list()
            ]
        }

    @application.get("/file/{repository}/{file_path:path}", response_model=FileResponse)
    def get_file(repository: str, file_path: str) -> dict[str, str]:
        try:
            content = active_runtime.repositories.read_file(repository, file_path)
        except RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"repository": repository, "path": file_path, "content": content}

    @application.post("/search", response_model=SearchResponse)
    async def search(request: SearchRequest) -> dict[str, Any]:
        limit = request.limit or active_settings.retrieval.default_limit
        if limit > active_settings.retrieval.max_limit:
            raise HTTPException(
                status_code=400,
                detail=(f"limit cannot exceed {active_settings.retrieval.max_limit}"),
            )
        try:
            return await active_runtime.retrieval.search(
                request.query, request.repository, limit
            )
        except RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except IndexStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (
            JetsonClientError,
            QdrantContractError,
            QdrantOperationError,
            RetrievalError,
        ) as exc:
            logger.error(
                "Search dependency failed",
                extra={
                    "event": "search_dependency_failed",
                    "repository": request.repository,
                    "error_type": type(exc).__name__,
                },
            )
            raise HTTPException(
                status_code=502, detail="Search dependency unavailable"
            ) from exc
        except Exception as exc:
            logger.exception(
                "Search failed",
                extra={
                    "event": "search_failed",
                    "repository": request.repository,
                },
            )
            raise HTTPException(status_code=500, detail="Search failed") from exc

    @application.post(
        "/index",
        response_model=IndexAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def trigger_index(request: IndexRequest) -> dict[str, str]:
        try:
            active_runtime.repositories.resolve(request.repository)
            job_id = active_runtime.jobs.submit(request.repository)
        except RepositoryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except JobConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "status": "accepted",
            "job_id": job_id,
            "repository": request.repository,
        }

    @application.get("/index-status")
    def list_jobs() -> dict[str, Any]:
        return {"jobs": active_runtime.state.list_jobs()}

    @application.get("/index-status/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = active_runtime.state.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Indexing job not found")
        return job

    return application
