"""Command-line entry point for authoritative repository indexing."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from .config import Settings
from .logging_config import configure_logging
from .runtime import SourceRecallRuntime


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Index one managed repository into SourceRecall."
    )
    command.add_argument("repository", help="Repository folder name")
    command.add_argument(
        "--config",
        type=Path,
        help="Configuration file (default: SOURCE_RECALL_CONFIG or /etc)",
    )
    return command


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    runtime: SourceRecallRuntime | None = None
    try:
        settings = Settings.load(args.config)
        configure_logging(settings.logging)
        runtime = SourceRecallRuntime(settings)
        runtime.startup()
        job_id = f"cli-{uuid.uuid4().hex}"
        runtime.state.create_job(job_id, args.repository)
        summary = runtime.indexer.index_repository(args.repository, job_id)
        print(
            f"Indexed {summary.repository}: {summary.files_indexed} files, "
            f"{summary.chunks_indexed} chunks, "
            f"{summary.stale_chunks_removed} stale chunks removed"
        )
        return 0
    except Exception as exc:
        print(f"SourceRecall indexing failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if runtime is not None:
            asyncio.run(runtime.shutdown())


if __name__ == "__main__":
    raise SystemExit(main())
