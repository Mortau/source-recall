from __future__ import annotations

import json
import logging

from source_recall.config import LoggingSettings
from source_recall.logging_config import JsonFormatter, configure_logging


def test_json_formatter_emits_structured_context() -> None:
    record = logging.LogRecord(
        "source_recall.test", logging.INFO, __file__, 1, "ready", (), None
    )
    record.event = "test_event"

    body = json.loads(JsonFormatter().format(record))

    assert body["message"] == "ready"
    assert body["event"] == "test_event"
    assert body["request_id"] == "-"


def test_logging_configuration_does_not_duplicate_handlers(tmp_path) -> None:
    settings = LoggingSettings("INFO", tmp_path / "source.log", 1024, 1)

    logger = configure_logging(settings)
    logger = configure_logging(settings)

    managed = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_source_recall_handler", False)
    ]
    assert len(managed) == 2
