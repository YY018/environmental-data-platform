"""Configuration loading: YAML files for settings, environment variables for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(RuntimeError):
    """Raised when required configuration or secrets are missing."""


@dataclass(frozen=True)
class AppConfig:
    settings: dict[str, Any]
    sources: dict[str, Any]
    project_root: Path = PROJECT_ROOT

    def path(self, key: str) -> Path:
        """Resolve a path from settings.paths relative to the project root."""
        return self.project_root / self.settings["paths"][key]


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Load settings.yaml and sources.yaml, and load .env into the environment.

    Values already present in the environment (e.g. GitHub Actions secrets)
    take precedence over .env, because load_dotenv does not override them.
    """
    config_dir = config_dir or PROJECT_ROOT / "config"
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    with open(config_dir / "settings.yaml", encoding="utf-8") as fh:
        settings = yaml.safe_load(fh)
    with open(config_dir / "sources.yaml", encoding="utf-8") as fh:
        sources = yaml.safe_load(fh)
    return AppConfig(settings=settings, sources=sources)


def get_secret(name: str) -> str:
    """Return a required secret from the environment, failing loudly if absent."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Environment variable {name} is not set. "
            "Add it to .env locally or to GitHub Secrets in CI."
        )
    return value
