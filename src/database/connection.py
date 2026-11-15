"""Database engine creation. The connection string comes only from DATABASE_URL."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from src.config import ConfigError, get_secret


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a shared SQLAlchemy engine for the configured database.

    - pool_pre_ping: Neon suspends idle compute; this detects dead connections
      and reconnects instead of failing the first query after a pause.
    - Every session runs in UTC so timestamps never depend on server settings.
    """
    raw = get_secret("DATABASE_URL")
    try:
        url = make_url(raw)
    except ArgumentError as exc:
        # Never echo the URL itself: it contains the password.
        raise ConfigError(
            "DATABASE_URL could not be parsed. Expected "
            "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require "
            "(no quotes, no leading 'psql')."
        ) from exc
    if url.drivername != "postgresql+psycopg":
        raise ConfigError(
            f"DATABASE_URL uses driver '{url.drivername}'; it must start with postgresql+psycopg://"
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
        connect_args={"options": "-c timezone=UTC", "connect_timeout": 15},
    )
