from __future__ import annotations

from pathlib import Path

import pytest

from source_recall.config import ConfigurationError, Settings


def test_defaults_match_production_contract() -> None:
    settings = Settings.from_mapping({})

    assert settings.repositories.root == Path("/srv/source-recall/repositories")
    assert settings.qdrant.collection == "source_recall_v1"
    assert settings.qdrant.embedding_dimensions == 384
    assert settings.jetson_nlp.rerank_enabled is True
    assert settings.state.database_path == Path(
        "/var/lib/source-recall/source-recall.db"
    )


def test_mapping_overrides_only_selected_values(tmp_path: Path) -> None:
    settings = Settings.from_mapping(
        {
            "repositories": {"root": str(tmp_path)},
            "logging": {"file": None},
            "security": {"api_token": "secret"},
        }
    )

    assert settings.repositories.root == tmp_path
    assert settings.logging.file is None
    assert settings.security.api_token == "secret"
    assert settings.retrieval.default_limit == 8


def test_unknown_configuration_key_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Unknown qdrant"):
        Settings.from_mapping({"qdrant": {"collections": "typo"}})


def test_unsafe_candidate_counts_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match="candidate counts"):
        Settings.from_mapping({"retrieval": {"vector_candidates": 2}})


def test_explicit_missing_configuration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        Settings.load(tmp_path / "missing.yaml")
