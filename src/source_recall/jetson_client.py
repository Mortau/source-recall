"""Validated clients for the Jetson NLP embedding and reranking API."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from .config import JetsonSettings, QdrantSettings
from .logging_config import current_request_id


class JetsonClientError(RuntimeError):
    """Raised when Jetson NLP is unavailable or violates its contract."""


class JetsonNlpClient:
    def __init__(
        self,
        settings: JetsonSettings,
        qdrant_settings: QdrantSettings,
        *,
        sync_transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.dimensions = qdrant_settings.embedding_dimensions
        self._sync_client = httpx.Client(
            base_url=settings.base_url,
            timeout=settings.index_timeout_seconds,
            transport=sync_transport,
        )
        self._async_client = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
            transport=async_transport,
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        request_id = current_request_id()
        return {"X-Request-ID": request_id} if request_id != "-" else {}

    def _parse_embeddings(
        self,
        body: Mapping[str, Any],
        expected_count: int,
    ) -> list[list[float]]:
        raw_items = body.get("data")
        if not isinstance(raw_items, list) or len(raw_items) != expected_count:
            raise JetsonClientError("Jetson returned an invalid embedding count")
        ordered: list[list[float] | None] = [None] * expected_count
        for item in raw_items:
            if not isinstance(item, Mapping):
                raise JetsonClientError("Jetson returned an invalid embedding item")
            index = item.get("index")
            vector = item.get("embedding")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < expected_count
                or ordered[index] is not None
                or not isinstance(vector, list)
                or len(vector) != self.dimensions
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in vector
                )
            ):
                raise JetsonClientError("Jetson embedding contract mismatch")
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise JetsonClientError("Jetson returned a non-numeric vector") from exc
            if not all(math.isfinite(value) for value in values):
                raise JetsonClientError("Jetson returned a non-finite vector")
            norm = math.sqrt(sum(value * value for value in values))
            if not 0.98 <= norm <= 1.02:
                raise JetsonClientError("Jetson returned a non-normalized vector")
            ordered[index] = values
        if any(vector is None for vector in ordered):
            raise JetsonClientError("Jetson omitted an embedding index")
        return [vector for vector in ordered if vector is not None]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = self._sync_client.post(
                "/v1/embeddings",
                json={"input": list(texts), "normalize": True},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JetsonClientError("Jetson embedding request failed") from exc
        if not isinstance(body, Mapping):
            raise JetsonClientError("Jetson returned invalid embedding JSON")
        return self._parse_embeddings(body, len(texts))

    async def embed_query(self, text: str) -> list[float]:
        try:
            response = await self._async_client.post(
                "/v1/embeddings",
                json={"input": [text], "normalize": True},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JetsonClientError("Jetson embedding request failed") from exc
        if not isinstance(body, Mapping):
            raise JetsonClientError("Jetson returned invalid embedding JSON")
        return self._parse_embeddings(body, 1)[0]

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
    ) -> list[tuple[int, float]]:
        try:
            response = await self._async_client.post(
                "/v1/rerank",
                json={"query": query, "documents": list(documents)},
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JetsonClientError("Jetson reranking request failed") from exc
        if not isinstance(body, Mapping) or not isinstance(body.get("results"), list):
            raise JetsonClientError("Jetson returned invalid reranking JSON")
        results: list[tuple[int, float]] = []
        seen: set[int] = set()
        for item in body["results"]:
            if not isinstance(item, Mapping):
                raise JetsonClientError("Jetson returned an invalid reranking item")
            index = item.get("index")
            score = item.get("score")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < len(documents)
                or index in seen
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                raise JetsonClientError("Jetson reranking contract mismatch")
            seen.add(index)
            results.append((index, float(score)))
        if seen != set(range(len(documents))):
            raise JetsonClientError("Jetson omitted a reranking index")
        if any(
            results[index][1] < results[index + 1][1]
            for index in range(len(results) - 1)
        ):
            raise JetsonClientError("Jetson reranking results are not descending")
        return results

    async def readiness(self) -> dict[str, Any]:
        try:
            response = await self._async_client.get("/ready", headers=self._headers())
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JetsonClientError("Jetson readiness request failed") from exc
        if response.status_code != 200 or not isinstance(body, dict):
            raise JetsonClientError("Jetson NLP is not ready")
        return body

    async def close(self) -> None:
        self._sync_client.close()
        await self._async_client.aclose()
