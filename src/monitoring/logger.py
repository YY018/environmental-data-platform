"""Structured logging: readable console output plus JSON lines in a log file.

Usage:
    configure_logging(level="INFO", log_file=Path("logs/pipeline.log"))
    log = logging.getLogger(__name__)
    log.info("request complete", extra={"source": "usgs", "status": 200})

Fields passed via ``extra`` appear as keys in the JSON log, which makes the
file easy to filter (e.g. all failed requests for one source).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# Attributes every LogRecord has; anything else came from ``extra``.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable line with extra fields appended as key=value."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        if extras:
            base += " | " + " ".join(f"{k}={v}" for k, v in extras.items())
        return base


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure the root logger once. Safe to call repeatedly."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(
        ConsoleFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    )
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    # urllib3 logs every connection at DEBUG; keep it quiet unless debugging.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
