"""Shared test helpers: a fake HTTP session that replays scripted responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests
from requests.structures import CaseInsensitiveDict

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_response(status: int = 200, body: Any = None, headers: dict | None = None,
                  url: str = "https://example.test") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body if body is not None else {}).encode()
    response.headers = CaseInsensitiveDict(headers or {})
    response.url = url
    return response


class FakeSession:
    """Stands in for requests.Session. Each get() pops the next scripted item;
    an Exception instance is raised instead of returned."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if not self.script:
            raise AssertionError(f"Unexpected extra request to {url} {params}")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def make_client():
    """Build an HttpClient over a FakeSession; sleeps are recorded, not performed."""
    from src.extract.http_client import HttpClient

    def _make(script: list, max_retries: int = 3):
        session = FakeSession(script)
        sleeps: list[float] = []
        client = HttpClient(max_retries=max_retries, backoff_min_seconds=1,
                            backoff_max_seconds=60, session=session, sleep=sleeps.append)
        return client, session, sleeps

    return _make


@pytest.fixture
def raw_store(tmp_path):
    from src.extract.common import RawStore

    return RawStore(tmp_path / "raw")
