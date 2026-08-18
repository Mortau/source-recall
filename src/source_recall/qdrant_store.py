"""Qdrant persistence with explicit collection and payload contracts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from .config import IndexSettings, JetsonSettings, QdrantSettings
from .models import ChunkRecord, SearchCandidate


class QdrantContractError(RuntimeError):
    """Raised when Qdrant does not match the configured vector contract."""


class QdrantOperationError(RuntimeError):
    """Raised when a Qdrant request cannot be completed."""


class QdrantStore:
    def __init__(
        self,
        settings: QdrantSettings,
        jetson_settings: JetsonSettings,
        index_settings: IndexSettings,
        client: QdrantClient | None = None,
    ):
        self.settings = settings
        self.jetson_settings = jetson_settings
        self.index_settings = index_settings
        self.client = client or QdrantClient(
            url=settings.url,
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
        )

    def health(self) -> None:
        self.client.get_collections()

    @staticmethod
    def _distance_value(value: object) -> str:
        return str(getattr(value, "value", value)).lower()

    def ensure_collection(self) -> None:
        names = {item.name for item in self.client.get_collections().collections}
        if self.settings.collection not in names:
            self.client.create_collection(
                collection_name=self.settings.collection,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            for field_name, schema in (
                ("repository", PayloadSchemaType.KEYWORD),
                ("path", PayloadSchemaType.KEYWORD),
                ("index_generation", PayloadSchemaType.KEYWORD),
                ("embedding_model", PayloadSchemaType.KEYWORD),
                ("chunker_version", PayloadSchemaType.KEYWORD),
                ("schema_version", PayloadSchemaType.INTEGER),
            ):
                self.client.create_payload_index(
                    collection_name=self.settings.collection,
                    field_name=field_name,
                    field_schema=schema,
                    wait=True,
                )
            return

        info = self.client.get_collection(self.settings.collection)
        vectors = info.config.params.vectors
        if isinstance(vectors, dict):
            raise QdrantContractError(
                "SourceRecall requires an unnamed single-vector collection"
            )
        size = getattr(vectors, "size", None)
        distance = self._distance_value(getattr(vectors, "distance", ""))
        if size != self.settings.embedding_dimensions or distance != "cosine":
            raise QdrantContractError(
                "Existing Qdrant collection does not match the configured "
                "dimension and cosine-distance contract"
            )

    def _contract_conditions(self) -> list[FieldCondition]:
        return [
            FieldCondition(
                key="embedding_model",
                match=MatchValue(value=self.jetson_settings.embedding_model),
            ),
            FieldCondition(
                key="schema_version",
                match=MatchValue(value=self.index_settings.schema_version),
            ),
            FieldCondition(
                key="chunker_version",
                match=MatchValue(value=self.index_settings.chunker_version),
            ),
        ]

    def query(
        self,
        repository: str,
        index_generation: str,
        vector: list[float],
        limit: int,
    ) -> list[SearchCandidate]:
        conditions = [
            FieldCondition(key="repository", match=MatchValue(value=repository)),
            FieldCondition(
                key="index_generation",
                match=MatchValue(value=index_generation),
            ),
            *self._contract_conditions(),
        ]
        try:
            response = self.client.query_points(
                collection_name=self.settings.collection,
                query=vector,
                query_filter=Filter(must=conditions),
                limit=limit,
                with_payload=True,
            )
        except ApiException as exc:
            raise QdrantOperationError("Qdrant vector search failed") from exc
        candidates: list[SearchCandidate] = []
        for point in response.points:
            payload = point.payload or {}
            try:
                candidates.append(
                    SearchCandidate(
                        repository=str(payload["repository"]),
                        path=str(payload["path"]),
                        start_line=int(payload["start_line"]),
                        end_line=int(payload["end_line"]),
                        content=str(payload["content"]),
                        sources={"vector"},
                        vector_score=float(point.score),
                        metadata={
                            "indexed_commit": payload.get("indexed_commit"),
                            "file_checksum": payload.get("file_checksum"),
                        },
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return candidates

    def upsert(
        self,
        records: Sequence[ChunkRecord],
        vectors: Sequence[list[float]],
    ) -> None:
        if len(records) != len(vectors):
            raise QdrantContractError("Record and vector counts do not match")
        points = [
            PointStruct(
                id=record.point_id,
                vector=vector,
                payload={
                    "repository": record.repository,
                    "index_generation": record.index_generation,
                    "path": record.path,
                    "sequence": record.sequence,
                    "start_line": record.start_line,
                    "end_line": record.end_line,
                    "content": record.content,
                    "file_checksum": record.file_checksum,
                    "content_checksum": record.content_checksum,
                    "indexed_commit": record.indexed_commit,
                    "embedding_model": self.jetson_settings.embedding_model,
                    "embedding_dimensions": self.settings.embedding_dimensions,
                    "schema_version": self.index_settings.schema_version,
                    "chunker_version": self.index_settings.chunker_version,
                },
            )
            for record, vector in zip(records, vectors, strict=True)
        ]
        self.client.upsert(
            collection_name=self.settings.collection,
            points=points,
            wait=True,
        )

    def repository_point_ids(self, repository: str) -> set[str]:
        point_ids: set[str] = set()
        offset: Any = None
        repository_filter = Filter(
            must=[FieldCondition(key="repository", match=MatchValue(value=repository))]
        )
        while True:
            points, offset = self.client.scroll(
                collection_name=self.settings.collection,
                scroll_filter=repository_filter,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.update(str(point.id) for point in points)
            if offset is None:
                return point_ids

    def delete_ids(self, point_ids: set[str]) -> int:
        ordered = sorted(point_ids)
        for offset in range(0, len(ordered), 256):
            self.client.delete(
                collection_name=self.settings.collection,
                points_selector=PointIdsList(points=ordered[offset : offset + 256]),
                wait=True,
            )
        return len(ordered)

    def close(self) -> None:
        self.client.close()
