"""Phase 1 smoke tests: the environment, configuration and secret handling are sane."""

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_running_inside_virtualenv() -> None:
    assert sys.prefix != sys.base_prefix, "Tests must run inside the .venv interpreter"


def test_core_libraries_import() -> None:
    import dotenv  # noqa: F401
    import pandas  # noqa: F401
    import psycopg  # noqa: F401
    import requests  # noqa: F401
    import sqlalchemy  # noqa: F401
    import tenacity  # noqa: F401


def test_config_files_parse() -> None:
    settings = yaml.safe_load((PROJECT_ROOT / "config" / "settings.yaml").read_text())
    sources = yaml.safe_load((PROJECT_ROOT / "config" / "sources.yaml").read_text())
    assert settings["backfill"]["start_date"] < settings["backfill"]["end_date"]
    assert set(sources) == {"open_meteo", "openaq", "usgs"}
    assert len(sources["open_meteo"]["locations"]) == 10


def test_secrets_are_git_ignored() -> None:
    for path in (".env", ".venv", "data/raw/usgs/sample.json", "logs/run.log"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT, check=False
        )
        assert result.returncode == 0, f"{path} is NOT ignored by git"
