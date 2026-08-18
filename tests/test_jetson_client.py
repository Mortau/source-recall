from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from source_recall.config import Settings
from source_recall.jetson_client import JetsonClientError, JetsonNlpClient


def settings() -> Settings:
    return Settings.from_mapping(
        {
            "qdrant": {"embedding_dimensions": 3},
            "logging": {"file": None},
        }
    )


def client(handler) -> JetsonNlpClient:
    active = settings()
    transport = httpx.MockTransport(handler)
    return JetsonNlpClient(
        active.jetson_nlp,
        active.qdrant,
        sync_transport=transport,
        async_transport=transport,
    )


def test_embedding_contract_preserves_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["normalize"] is True
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            },
        )

    active = client(handler)
    try:
        assert active.embed_batch(["first", "second"]) == [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    finally:
        asyncio.run(active.close())


def test_embedding_contract_rejects_wrong_dimension() -> None:
    active = client(
        lambda request: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0]}]}
        )
    )
    try:
        with pytest.raises(JetsonClientError, match="contract"):
            active.embed_batch(["first"])
    finally:
        asyncio.run(active.close())


def test_embedding_contract_rejects_boolean_values() -> None:
    active = client(
        lambda request: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [True, 0.0, 0.0]}]}
        )
    )
    try:
        with pytest.raises(JetsonClientError, match="contract"):
            active.embed_batch(["first"])
    finally:
        asyncio.run(active.close())


def test_reranker_contract_is_complete_and_descending() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/rerank"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "score": 0.9},
                    {"index": 0, "score": 0.2},
                ]
            },
        )

    active = client(handler)
    try:
        result = asyncio.run(active.rerank("query", ["a", "b"]))
        assert result == [(1, 0.9), (0, 0.2)]
    finally:
        asyncio.run(active.close())
