"""Structured console and rotating-file logging."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any

from .config import LoggingSettings

REQUEST_ID: ContextVar[str] = ContextVar("source_recall_request_id", default="-")

_STANDARD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
_STANDARD_FIELDS.update({"message", "asctime"})


class JsonFormatter(logging.Formatter):
    """Render one newline-delimited JSON event."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", REQUEST_ID.get()),
        }
        for name, value in record.__dict__.items():
            if name not in _STANDARD_FIELDS and name not in payload:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = REQUEST_ID.get()
        return True


def set_request_id(request_id: str) -> Token[str]:
    return REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    REQUEST_ID.reset(token)


def current_request_id() -> str:
    return REQUEST_ID.get()


def _prepare(handler: logging.Handler, formatter: JsonFormatter) -> None:
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())
    handler._source_recall_handler = True


def configure_logging(settings: LoggingSettings) -> logging.Logger:
    """Configure SourceRecall logging without duplicating handlers."""

    logger = logging.getLogger("source_recall")
    logger.setLevel(settings.level)
    logger.propagate = False
    for handler in list(logger.handlers):
        if getattr(handler, "_source_recall_handler", False):
            logger.removeHandler(handler)
            handler.close()

    formatter = JsonFormatter()
    console = logging.StreamHandler(sys.stdout)
    _prepare(console, formatter)
    logger.addHandler(console)

    if settings.file is not None:
        try:
            settings.file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                settings.file,
                maxBytes=settings.max_bytes,
                backupCount=settings.backup_count,
                encoding="utf-8",
            )
            _prepare(file_handler, formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.error(
                "File logging unavailable; using console logging",
                extra={
                    "event": "logging_file_unavailable",
                    "path": str(settings.file),
                    "error_type": type(exc).__name__,
                },
            )

    logger.info(
        "Logging configured",
        extra={
            "event": "logging_configured",
            "level_name": settings.level,
            "file": str(settings.file) if settings.file else None,
        },
    )
    return logger
