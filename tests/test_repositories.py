from __future__ import annotations

from pathlib import Path

import pytest

from source_recall.config import Settings
from source_recall.repositories import (
    RepositoryError,
    RepositoryManager,
    validate_repository_name,
)


def manager(tmp_path: Path) -> RepositoryManager:
    settings = Settings.from_mapping(
        {"repositories": {"root": str(tmp_path)}, "logging": {"file": None}}
    )
    return RepositoryManager(settings.repositories)


@pytest.mark.parametrize(
    "name", ["../etc", "/etc", "nested/repo", "nested\\repo", ".", "..", ""]
)
def test_repository_name_rejects_path_traversal(name: str) -> None:
    with pytest.raises(RepositoryError):
        validate_repository_name(name)


def test_repository_and_file_resolution_stay_under_root(tmp_path: Path) -> None:
    repository = tmp_path / "example-project"
    source = repository / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('safe')\n", encoding="utf-8")
    repositories = manager(tmp_path)

    assert repositories.resolve("example-project") == repository.resolve()
    assert repositories.read_file("example-project", "src/app.py") == (
        "print('safe')\n"
    )
    with pytest.raises(RepositoryError):
        repositories.resolve_file("example-project", "../outside.py")
    with pytest.raises(RepositoryError):
        repositories.resolve_file("example-project", "/etc/passwd")


def test_list_returns_only_safe_directories(tmp_path: Path) -> None:
    (tmp_path / "z-repo").mkdir()
    (tmp_path / "a_repo").mkdir()
    (tmp_path / "not a repo").mkdir()

    assert manager(tmp_path).list() == ["a_repo", "z-repo"]
