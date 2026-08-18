"""Validated YAML configuration for SourceRecall."""

from __future__ import annotations

import copy
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/source-recall/source-recall.yaml")

DEFAULTS: dict[str, Any] = {
    "service": {"host": "0.0.0.0", "port": 8070},
    "repositories": {
        "root": "/srv/source-recall/repositories",
        "git_tracked_only": True,
        "require_clean_git": True,
        "max_file_bytes": 1_048_576,
        "include_extensions": [
            ".c",
            ".cpp",
            ".go",
            ".h",
            ".hpp",
            ".java",
            ".js",
            ".json",
            ".md",
            ".py",
            ".rs",
            ".toml",
            ".ts",
            ".tsx",
            ".yaml",
            ".yml",
        ],
        "exclude_dirs": [
            ".git",
            ".idea",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            ".vscode",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
            "vendor",
        ],
    },
    "qdrant": {
        "url": "http://127.0.0.1:6333",
        "collection": "source_recall_v1",
        "api_key": None,
        "timeout_seconds": 30.0,
        "embedding_dimensions": 384,
    },
    "jetson_nlp": {
        "base_url": "http://192.168.20.72:8091",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "request_timeout_seconds": 30.0,
        "index_timeout_seconds": 120.0,
        "rerank_enabled": True,
    },
    "indexing": {
        "batch_size": 16,
        "chunk_max_characters": 2_000,
        "chunk_overlap_lines": 5,
        "schema_version": 1,
        "chunker_version": "line-v1",
    },
    "retrieval": {
        "default_limit": 8,
        "max_limit": 20,
        "vector_candidates": 20,
        "lexical_candidates": 20,
        "rerank_candidates": 20,
        "rrf_k": 60,
        "lexical_context_lines": 20,
        "lexical_timeout_seconds": 10.0,
    },
    "state": {
        "database_path": "/var/lib/source-recall/source-recall.db",
        "job_history_limit": 100,
    },
    "logging": {
        "level": "INFO",
        "file": "/var/log/source-recall/source-recall.log",
        "max_bytes": 10_485_760,
        "backup_count": 5,
    },
    "security": {"api_token": None},
    "mcp": {
        "api_url": "http://127.0.0.1:8070",
        "transport": "http",
        "host": "0.0.0.0",
        "port": 8071,
        "path": "/mcp/",
    },
}


class ConfigurationError(RuntimeError):
    """Raised when the configuration is missing or unsafe."""


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a mapping")
    return value


def _merge(base: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    unknown = set(overrides) - set(base)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"Unknown configuration section(s): {names}")
    for section_name, section_value in overrides.items():
        default_section = _mapping(base[section_name], section_name)
        override_section = _mapping(section_value, section_name)
        unknown_keys = set(override_section) - set(default_section)
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise ConfigurationError(
                f"Unknown {section_name} configuration key(s): {names}"
            )
        merged[section_name].update(override_section)
    return merged


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _integer(value: object, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: object, name: str, minimum: float = 0.1) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be numeric")
    result = float(value)
    if result < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return result


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(f"{name} must be true or false")
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{name} must be a non-empty list")
    return tuple(_text(item, name) for item in value)


@dataclass(frozen=True)
class ServiceSettings:
    host: str
    port: int


@dataclass(frozen=True)
class RepositorySettings:
    root: Path
    git_tracked_only: bool
    require_clean_git: bool
    max_file_bytes: int
    include_extensions: frozenset[str]
    exclude_dirs: frozenset[str]


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    collection: str
    api_key: str | None
    timeout_seconds: float
    embedding_dimensions: int


@dataclass(frozen=True)
class JetsonSettings:
    base_url: str
    embedding_model: str
    request_timeout_seconds: float
    index_timeout_seconds: float
    rerank_enabled: bool


@dataclass(frozen=True)
class IndexSettings:
    batch_size: int
    chunk_max_characters: int
    chunk_overlap_lines: int
    schema_version: int
    chunker_version: str


@dataclass(frozen=True)
class RetrievalSettings:
    default_limit: int
    max_limit: int
    vector_candidates: int
    lexical_candidates: int
    rerank_candidates: int
    rrf_k: int
    lexical_context_lines: int
    lexical_timeout_seconds: float


@dataclass(frozen=True)
class StateSettings:
    database_path: Path
    job_history_limit: int


@dataclass(frozen=True)
class LoggingSettings:
    level: str
    file: Path | None
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class SecuritySettings:
    api_token: str | None


@dataclass(frozen=True)
class McpSettings:
    api_url: str
    transport: str
    host: str
    port: int
    path: str


@dataclass(frozen=True)
class Settings:
    """Complete immutable configuration for one SourceRecall process."""

    service: ServiceSettings
    repositories: RepositorySettings
    qdrant: QdrantSettings
    jetson_nlp: JetsonSettings
    indexing: IndexSettings
    retrieval: RetrievalSettings
    state: StateSettings
    logging: LoggingSettings
    security: SecuritySettings
    mcp: McpSettings
    config_path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        env_path = os.environ.get("SOURCE_RECALL_CONFIG")
        selected = path or (Path(env_path) if env_path else DEFAULT_CONFIG_PATH)
        required = path is not None or env_path is not None
        if selected.exists():
            try:
                raw = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise ConfigurationError(
                    f"Unable to read configuration: {selected}"
                ) from exc
            return cls.from_mapping(_mapping(raw, "configuration"), selected)
        if required:
            raise ConfigurationError(f"Configuration file not found: {selected}")
        return cls.from_mapping({}, None)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        config_path: Path | None = None,
    ) -> Settings:
        data = _merge(DEFAULTS, values)
        service = data["service"]
        repositories = data["repositories"]
        qdrant = data["qdrant"]
        jetson = data["jetson_nlp"]
        indexing = data["indexing"]
        retrieval = data["retrieval"]
        state = data["state"]
        logging = data["logging"]
        security = data["security"]
        mcp = data["mcp"]

        extensions = {
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in _string_tuple(
                repositories["include_extensions"],
                "repositories.include_extensions",
            )
        }
        settings = cls(
            service=ServiceSettings(
                host=_text(service["host"], "service.host"),
                port=_integer(service["port"], "service.port"),
            ),
            repositories=RepositorySettings(
                root=Path(_text(repositories["root"], "repositories.root")),
                git_tracked_only=_boolean(
                    repositories["git_tracked_only"],
                    "repositories.git_tracked_only",
                ),
                require_clean_git=_boolean(
                    repositories["require_clean_git"],
                    "repositories.require_clean_git",
                ),
                max_file_bytes=_integer(
                    repositories["max_file_bytes"],
                    "repositories.max_file_bytes",
                ),
                include_extensions=frozenset(extensions),
                exclude_dirs=frozenset(
                    _string_tuple(
                        repositories["exclude_dirs"],
                        "repositories.exclude_dirs",
                    )
                ),
            ),
            qdrant=QdrantSettings(
                url=_text(qdrant["url"], "qdrant.url").rstrip("/"),
                collection=_text(qdrant["collection"], "qdrant.collection"),
                api_key=_optional_text(qdrant["api_key"], "qdrant.api_key"),
                timeout_seconds=_number(
                    qdrant["timeout_seconds"], "qdrant.timeout_seconds"
                ),
                embedding_dimensions=_integer(
                    qdrant["embedding_dimensions"],
                    "qdrant.embedding_dimensions",
                ),
            ),
            jetson_nlp=JetsonSettings(
                base_url=_text(jetson["base_url"], "jetson_nlp.base_url").rstrip("/"),
                embedding_model=_text(
                    jetson["embedding_model"],
                    "jetson_nlp.embedding_model",
                ),
                request_timeout_seconds=_number(
                    jetson["request_timeout_seconds"],
                    "jetson_nlp.request_timeout_seconds",
                ),
                index_timeout_seconds=_number(
                    jetson["index_timeout_seconds"],
                    "jetson_nlp.index_timeout_seconds",
                ),
                rerank_enabled=_boolean(
                    jetson["rerank_enabled"],
                    "jetson_nlp.rerank_enabled",
                ),
            ),
            indexing=IndexSettings(
                batch_size=_integer(indexing["batch_size"], "indexing.batch_size"),
                chunk_max_characters=_integer(
                    indexing["chunk_max_characters"],
                    "indexing.chunk_max_characters",
                ),
                chunk_overlap_lines=_integer(
                    indexing["chunk_overlap_lines"],
                    "indexing.chunk_overlap_lines",
                    minimum=0,
                ),
                schema_version=_integer(
                    indexing["schema_version"], "indexing.schema_version"
                ),
                chunker_version=_text(
                    indexing["chunker_version"], "indexing.chunker_version"
                ),
            ),
            retrieval=RetrievalSettings(
                default_limit=_integer(
                    retrieval["default_limit"], "retrieval.default_limit"
                ),
                max_limit=_integer(retrieval["max_limit"], "retrieval.max_limit"),
                vector_candidates=_integer(
                    retrieval["vector_candidates"],
                    "retrieval.vector_candidates",
                ),
                lexical_candidates=_integer(
                    retrieval["lexical_candidates"],
                    "retrieval.lexical_candidates",
                ),
                rerank_candidates=_integer(
                    retrieval["rerank_candidates"],
                    "retrieval.rerank_candidates",
                ),
                rrf_k=_integer(retrieval["rrf_k"], "retrieval.rrf_k"),
                lexical_context_lines=_integer(
                    retrieval["lexical_context_lines"],
                    "retrieval.lexical_context_lines",
                    minimum=0,
                ),
                lexical_timeout_seconds=_number(
                    retrieval["lexical_timeout_seconds"],
                    "retrieval.lexical_timeout_seconds",
                ),
            ),
            state=StateSettings(
                database_path=Path(
                    _text(state["database_path"], "state.database_path")
                ),
                job_history_limit=_integer(
                    state["job_history_limit"], "state.job_history_limit"
                ),
            ),
            logging=LoggingSettings(
                level=_text(logging["level"], "logging.level").upper(),
                file=(
                    Path(file_value)
                    if (file_value := _optional_text(logging["file"], "logging.file"))
                    else None
                ),
                max_bytes=_integer(logging["max_bytes"], "logging.max_bytes"),
                backup_count=_integer(
                    logging["backup_count"],
                    "logging.backup_count",
                    minimum=0,
                ),
            ),
            security=SecuritySettings(
                api_token=_optional_text(security["api_token"], "security.api_token")
            ),
            mcp=McpSettings(
                api_url=_text(mcp["api_url"], "mcp.api_url").rstrip("/"),
                transport=_text(mcp["transport"], "mcp.transport").lower(),
                host=_text(mcp["host"], "mcp.host"),
                port=_integer(mcp["port"], "mcp.port"),
                path=_text(mcp["path"], "mcp.path"),
            ),
            config_path=config_path,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 1 <= self.service.port <= 65_535:
            raise ConfigurationError("service.port must be <= 65535")
        if not 1 <= self.mcp.port <= 65_535:
            raise ConfigurationError("mcp.port must be <= 65535")
        if self.mcp.transport not in {"stdio", "http"}:
            raise ConfigurationError("mcp.transport must be stdio or http")
        if not self.mcp.path.startswith("/"):
            raise ConfigurationError("mcp.path must start with /")
        if self.retrieval.default_limit > self.retrieval.max_limit:
            raise ConfigurationError(
                "retrieval.default_limit cannot exceed retrieval.max_limit"
            )
        candidate_counts = (
            self.retrieval.vector_candidates,
            self.retrieval.lexical_candidates,
            self.retrieval.rerank_candidates,
        )
        if min(candidate_counts) < self.retrieval.max_limit:
            raise ConfigurationError(
                "retrieval candidate counts must be >= retrieval.max_limit"
            )
        if self.retrieval.rerank_candidates > 64:
            raise ConfigurationError(
                "retrieval.rerank_candidates cannot exceed the Jetson limit of 64"
            )
        if self.indexing.chunk_max_characters > 16_000:
            raise ConfigurationError(
                "indexing.chunk_max_characters cannot exceed the Jetson text limit"
            )
        if self.indexing.batch_size > 32:
            raise ConfigurationError(
                "indexing.batch_size cannot exceed the Jetson input limit of 32"
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.qdrant.collection):
            raise ConfigurationError("qdrant.collection contains unsafe characters")
        if self.logging.level not in {
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
        }:
            raise ConfigurationError(f"Unsupported logging.level: {self.logging.level}")
