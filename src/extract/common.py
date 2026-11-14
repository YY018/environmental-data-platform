"""Building blocks shared by all extractors: date windows, results and raw storage."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


class ValidationError(RuntimeError):
    """Raised when an API response does not have the structure we depend on."""


def date_windows(start: date, end: date, window_days: int) -> Iterator[tuple[date, date]]:
    """Split the inclusive range [start, end] into consecutive inclusive windows.

    Example: 2026-01-01..2026-01-05 with window_days=2 gives
    (01-01, 01-02), (01-03, 01-04), (01-05, 01-05).
    """
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=window_days - 1), end)
        yield current, window_end
        current = window_end + timedelta(days=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExtractResult:
    """One validated API response plus the metadata needed to trace and reload it."""

    source: str
    entity: str                 # location name / sensor id / "global"
    window_start: date
    window_end: date
    request_url: str
    request_params: dict[str, Any]
    retrieved_at: datetime
    payload: Any
    record_count: int
    page: int = 1
    raw_path: Path | None = field(default=None)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


class RawStore:
    """Writes each API response to data/raw/<source>/retrieved=<date>/<file>.json.

    Files are partitioned by retrieval date so re-fetches never overwrite the
    evidence of an earlier run. Only request params are stored; auth headers
    are never part of the record.
    """

    def __init__(self, root: Path, enabled: bool = True):
        self.root = root
        self.enabled = enabled

    def save(self, result: ExtractResult) -> Path | None:
        if not self.enabled:
            return None
        folder = self.root / result.source / f"retrieved={result.retrieved_at:%Y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{_slug(result.entity)}_{result.window_start}_{result.window_end}_p{result.page}.json"
        path = folder / name
        document = {
            "metadata": {
                "source": result.source,
                "entity": result.entity,
                "window_start": result.window_start.isoformat(),
                "window_end": result.window_end.isoformat(),
                "page": result.page,
                "request_url": result.request_url,
                "request_params": result.request_params,
                "retrieved_at": result.retrieved_at.isoformat(),
                "record_count": result.record_count,
            },
            "payload": result.payload,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # atomic rename: no half-written files on crash
        result.raw_path = path
        return path
