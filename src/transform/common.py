"""Small parsing helpers shared by the source transforms."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp (with or without 'Z') into an aware UTC datetime."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_epoch_ms(value: int | float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def fix_mojibake(text: str | None) -> str | None:
    """Undo UTF-8 bytes that were decoded as Latin-1 ('Âµg/mÂ³' -> 'µg/m³').

    Returns the input unchanged when it is not mojibake.
    """
    if text is None:
        return None
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    """Return data[k1][k2]... or None when any level is missing or null."""
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
