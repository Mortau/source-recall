"""Safe repository and file resolution beneath the configured root."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .config import RepositorySettings

REPOSITORY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class RepositoryError(ValueError):
    """Raised when a repository or file path is invalid or unavailable."""


def validate_repository_name(name: str) -> str:
    candidate = name.strip()
    if candidate in {".", ".."} or not REPOSITORY_NAME.fullmatch(candidate):
        raise RepositoryError(
            "Repository must be a single safe folder name using letters, "
            "numbers, dots, underscores, or hyphens"
        )
    return candidate


class RepositoryManager:
    def __init__(self, settings: RepositorySettings):
        self.settings = settings

    @property
    def root(self) -> Path:
        return self.settings.root.resolve()

    def resolve(self, name: str) -> Path:
        safe_name = validate_repository_name(name)
        root = self.root
        candidate = (root / safe_name).resolve()
        if candidate.parent != root:
            raise RepositoryError("Repository resolves outside the managed root")
        if not candidate.is_dir():
            raise RepositoryError(f"Repository not found: {safe_name}")
        return candidate

    def list(self) -> list[str]:
        root = self.root
        if not root.is_dir():
            return []
        repositories: list[str] = []
        for path in root.iterdir():
            if not path.is_dir() or not REPOSITORY_NAME.fullmatch(path.name):
                continue
            try:
                if path.resolve().parent == root:
                    repositories.append(path.name)
            except OSError:
                continue
        return sorted(repositories, key=str.casefold)

    def resolve_file(self, repository: str, relative_path: str) -> Path:
        repo_root = self.resolve(repository)
        pure_path = PurePosixPath(relative_path)
        if (
            not relative_path.strip()
            or pure_path.is_absolute()
            or "\\" in relative_path
            or any(part in {"", ".", ".."} for part in pure_path.parts)
        ):
            raise RepositoryError("File path must be a safe repository-relative path")
        candidate = (repo_root / Path(*pure_path.parts)).resolve()
        if not candidate.is_relative_to(repo_root) or not candidate.is_file():
            raise RepositoryError("File not found beneath the repository root")
        return candidate

    def read_file(self, repository: str, relative_path: str) -> str:
        path = self.resolve_file(repository, relative_path)
        try:
            size = path.stat().st_size
            if size > self.settings.max_file_bytes:
                raise RepositoryError(
                    f"File exceeds {self.settings.max_file_bytes} bytes"
                )
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryError("File is not valid UTF-8 text") from exc
        except OSError as exc:
            raise RepositoryError("Unable to read file") from exc
