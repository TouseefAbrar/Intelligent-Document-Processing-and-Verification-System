"""Structured logging setup used across the application."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from app.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class UtcFormatter(logging.Formatter):
    """Formatter that logs timestamps in UTC ISO-8601 format."""

    converter = lambda *args: datetime.now(timezone.utc).timetuple()  # noqa: E731

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat(timespec="milliseconds")


def setup_logging(level: str | None = None) -> None:
    level = (level or settings.LOG_LEVEL or "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(UtcFormatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("app").setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"app.{name}")
