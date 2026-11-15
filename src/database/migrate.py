"""Apply SQL migrations in order, exactly once each.

Run: python -m src.database.migrate

Each file in sql/migrations runs in its own transaction and is recorded in
monitoring.schema_migrations with a checksum. Editing an applied file is
refused: schema changes go in a new numbered file, so every environment
(local, CI, production) ends up with the same schema.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import Engine, text

from src.config import PROJECT_ROOT
from src.database.connection import get_engine

log = logging.getLogger(__name__)
MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"


def _checksum(sql: str) -> str:
    # Normalise line endings so Windows/Linux checkouts give the same hash.
    return hashlib.sha256(sql.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def apply_migrations(engine: Engine, directory: Path = MIGRATIONS_DIR) -> list[str]:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS monitoring.schema_migrations (
                filename    TEXT PRIMARY KEY,
                checksum    TEXT        NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""))
        applied = dict(conn.execute(text("SELECT filename, checksum FROM monitoring.schema_migrations")).all())

    newly_applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        if path.name in applied:
            if applied[path.name] != checksum:
                raise RuntimeError(f"{path.name} was modified after being applied; add a new migration instead")
            continue
        with engine.begin() as conn:  # one transaction per file: all or nothing
            conn.exec_driver_sql(sql)
            conn.execute(
                text("INSERT INTO monitoring.schema_migrations (filename, checksum) VALUES (:f, :c)"),
                {"f": path.name, "c": checksum},
            )
        log.info("applied migration", extra={"migration": path.name})
        newly_applied.append(path.name)
    return newly_applied


if __name__ == "__main__":
    from src.config import load_config
    from src.monitoring.logger import configure_logging

    load_config()  # loads .env so DATABASE_URL is available when run locally
    configure_logging("INFO")
    done = apply_migrations(get_engine())
    print(f"Applied {len(done)} migration(s): {done}" if done else "Database schema is up to date.")
