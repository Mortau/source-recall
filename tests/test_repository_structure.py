from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_repository_has_required_files() -> None:
    required = {
        ".github/workflows/ci.yml",
        ".gitignore",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "MANIFEST.in",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
        "requirements.txt",
        "config/source-recall.yaml.example",
        "deploy/systemd/source-recall-api.service",
        "deploy/systemd/source-recall-mcp.service",
        "docs/api.md",
        "docs/architecture.md",
        "docs/configuration.md",
        "docs/deployment.md",
        "docs/development.md",
        "docs/operations.md",
    }
    missing = [path for path in required if not (ROOT / path).is_file()]

    assert missing == []


def test_legacy_prototype_files_are_removed() -> None:
    legacy = {
        "index_repo.py",
        "indexer.py",
        "mcp_server.py",
        "rag-api.service",
        "rag-config.yaml",
        "rag_api.py",
    }

    assert [path for path in legacy if (ROOT / path).exists()] == []


def test_systemd_units_use_the_documented_runtime_contract() -> None:
    api_unit = (ROOT / "deploy/systemd/source-recall-api.service").read_text(
        encoding="utf-8"
    )
    mcp_unit = (ROOT / "deploy/systemd/source-recall-mcp.service").read_text(
        encoding="utf-8"
    )

    for unit in (api_unit, mcp_unit):
        assert "WorkingDirectory=/opt/source-recall" in unit
        assert (
            "Environment=SOURCE_RECALL_CONFIG=/etc/source-recall/source-recall.yaml"
            in unit
        )
        environment_lines = [
            line for line in unit.splitlines() if line.startswith("Environment=")
        ]
        assert len(environment_lines) == 1

    assert "ReadOnlyPaths=/srv/source-recall/repositories" in api_unit
    assert "ReadWritePaths=/srv/source-recall/repositories" not in api_unit
