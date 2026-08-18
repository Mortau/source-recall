"""Serialized in-process indexing job execution backed by durable state."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

from .indexing import RepositoryIndexer
from .state import StateStore

logger = logging.getLogger("source_recall.jobs")


class JobManager:
    """Run one indexing job at a time and persist externally visible state."""

    def __init__(self, state: StateStore, indexer: RepositoryIndexer):
        self.state = state
        self.indexer = indexer
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="source-recall-index"
        )
        self._futures: set[Future[object]] = set()
        self._lock = Lock()

    def submit(self, repository: str) -> str:
        job_id = uuid.uuid4().hex
        self.state.create_job(job_id, repository)
        future = self._executor.submit(
            self.indexer.index_repository, repository, job_id
        )
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._finished)
        return job_id

    def _finished(self, future: Future[object]) -> None:
        with self._lock:
            self._futures.discard(future)
        try:
            future.result()
        except Exception:
            logger.error(
                "Background indexing job failed",
                extra={"event": "background_index_failed"},
            )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
