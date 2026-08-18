from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException

from source_recall.config import Settings
from source_recall.models import ChunkRecord
from source_recall.qdrant_store import (
    QdrantContractError,
    QdrantOperationError,
    QdrantStore,
)


class FakeClient:
    def __init__(self, *, existing: bool, size: int = 384):
        self.existing = existing
        self.size = size
        self.created = False
        self.indexes: list[str] = []

    def get_collections(self):
        collections = (
            [SimpleNamespace(name="source_recall_v1")] if self.existing else []
        )
        return SimpleNamespace(collections=collections)

    def create_collection(self, **kwargs) -> None:
        self.created = True

    def create_payload_index(self, *, field_name: str, **kwargs) -> None:
        self.indexes.append(field_name)

    def get_collection(self, collection: str):
        vectors = SimpleNamespace(size=self.size, distance="Cosine")
        return SimpleNamespace(
            config=SimpleNamespace(params=SimpleNamespace(vectors=vectors))
        )


def store(client: FakeClient) -> QdrantStore:
    settings = Settings.from_mapping({"logging": {"file": None}})
    return QdrantStore(
        settings.qdrant,
        settings.jetson_nlp,
        settings.indexing,
        client=client,
    )


def test_missing_collection_is_created_with_payload_indexes() -> None:
    client = FakeClient(existing=False)

    store(client).ensure_collection()

    assert client.created is True
    assert set(client.indexes) == {
        "repository",
        "path",
        "index_generation",
        "embedding_model",
        "chunker_version",
        "schema_version",
    }


def test_wrong_existing_vector_dimension_is_rejected() -> None:
    with pytest.raises(QdrantContractError, match="dimension"):
        store(FakeClient(existing=True, size=768)).ensure_collection()


def test_vector_search_dependency_failure_is_bounded() -> None:
    client = FakeClient(existing=True)
    client.query_points = lambda **kwargs: (_ for _ in ()).throw(
        ResponseHandlingException(OSError("offline"))
    )

    with pytest.raises(QdrantOperationError, match="vector search failed"):
        store(client).query("example", "generation-1", [1.0] * 384, 5)


def test_local_qdrant_round_trip_uses_index_generation() -> None:
    settings = Settings.from_mapping(
        {
            "qdrant": {
                "url": ":memory:",
                "collection": "test_collection",
                "embedding_dimensions": 3,
            },
            "logging": {"file": None},
        }
    )
    client = QdrantClient(":memory:")
    active = QdrantStore(
        settings.qdrant,
        settings.jetson_nlp,
        settings.indexing,
        client=client,
    )
    record = ChunkRecord(
        point_id="d8b48b72-39d9-4d5f-a2ae-7789b44c72c4",
        index_generation="generation-1",
        repository="example",
        path="app.py",
        sequence=0,
        start_line=1,
        end_line=2,
        content="def main():\n    pass",
        file_checksum="file",
        content_checksum="content",
        indexed_commit="abc123",
    )

    with pytest.warns(UserWarning, match="local Qdrant"):
        active.ensure_collection()
    active.upsert([record], [[1.0, 0.0, 0.0]])

    assert active.repository_point_ids("example") == {record.point_id}
    results = active.query("example", "generation-1", [1.0, 0.0, 0.0], 5)
    assert len(results) == 1
    assert results[0].path == "app.py"
    assert active.query("example", "other", [1.0, 0.0, 0.0], 5) == []
    assert active.delete_ids({record.point_id}) == 1
    assert active.repository_point_ids("example") == set()
