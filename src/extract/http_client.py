"""Shared HTTP client: timeouts, retries with backoff, status validation, rate limits.

Retry policy:
- Retried: connection errors, timeouts, HTTP 429 and 5xx (transient failures).
- Not retried: other 4xx (our request is wrong; retrying cannot fix it).
- HTTP 429 waits for the server-advertised reset time when one is given.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    """Non-retryable API failure (bad request, auth failure, invalid payload)."""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


class RetryableHttpError(RuntimeError):
    """Transient HTTP failure. ``retry_after`` is seconds the server asked us to wait."""

    def __init__(self, status: int, url: str, retry_after: float | None = None):
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    payload: Any
    elapsed_seconds: float


def _header_seconds(response: requests.Response, *names: str) -> float | None:
    for name in names:
        value = response.headers.get(name)  # requests headers are case-insensitive
        if value is not None:
            try:
                return max(0.0, float(value))
            except ValueError:
                continue
    return None


class _ServerAwareWait:
    """Use the server's Retry-After / reset hint if present, else exponential backoff."""

    def __init__(self, min_seconds: float, max_seconds: float):
        self._fallback = wait_exponential(multiplier=min_seconds, min=min_seconds, max=max_seconds)
        self._max = max_seconds

    def __call__(self, state: RetryCallState) -> float:
        exc = state.outcome.exception() if state.outcome else None
        if isinstance(exc, RetryableHttpError) and exc.retry_after is not None:
            return min(exc.retry_after + 1.0, self._max)
        return self._fallback(state)


class HttpClient:
    def __init__(
        self,
        timeout_seconds: float = 30,
        max_retries: int = 5,
        backoff_min_seconds: float = 2,
        backoff_max_seconds: float = 60,
        headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sleep = sleep
        self.timeout = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "environmental-data-platform/0.1"})
        if headers:
            self.session.headers.update(headers)

        self._get_with_retry = retry(
            retry=retry_if_exception_type(
                (RetryableHttpError, requests.ConnectionError, requests.Timeout)
            ),
            stop=stop_after_attempt(max_retries),
            wait=_ServerAwareWait(backoff_min_seconds, backoff_max_seconds),
            before_sleep=self._log_retry,
            sleep=sleep,
            reraise=True,
        )(self._get_once)

    @classmethod
    def from_settings(cls, http_settings: dict[str, Any], **kwargs: Any) -> "HttpClient":
        return cls(
            timeout_seconds=http_settings["timeout_seconds"],
            max_retries=http_settings["max_retries"],
            backoff_min_seconds=http_settings["backoff_min_seconds"],
            backoff_max_seconds=http_settings["backoff_max_seconds"],
            **kwargs,
        )

    @staticmethod
    def _log_retry(state: RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        log.warning(
            "retrying request",
            extra={
                "attempt": state.attempt_number,
                "error": str(exc),
                "sleep_seconds": round(state.next_action.sleep, 1) if state.next_action else None,
            },
        )

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> HttpResponse:
        """GET a URL and return parsed JSON, retrying transient failures."""
        return self._get_with_retry(url, params)

    def _get_once(self, url: str, params: dict[str, Any] | None) -> HttpResponse:
        started = time.monotonic()
        response = self.session.get(url, params=params, timeout=self.timeout)
        elapsed = time.monotonic() - started

        if response.status_code in RETRYABLE_STATUS:
            raise RetryableHttpError(
                response.status_code,
                response.url,
                retry_after=_header_seconds(response, "Retry-After", "X-Ratelimit-Reset")
                if response.status_code == 429
                else None,
            )
        if response.status_code >= 400:
            raise ApiError(
                f"HTTP {response.status_code} from {response.url}: {response.text[:300]}",
                status=response.status_code,
                url=response.url,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(f"Response from {response.url} is not valid JSON", url=response.url) from exc

        self._respect_rate_limit(response)
        log.debug(
            "request ok",
            extra={"url": response.url, "status": response.status_code, "elapsed_s": round(elapsed, 2)},
        )
        return HttpResponse(response.url, response.status_code, payload, elapsed)

    def _respect_rate_limit(self, response: requests.Response) -> None:
        """Pause proactively when the server says the quota is almost used up."""
        remaining = _header_seconds(response, "X-Ratelimit-Remaining")
        reset = _header_seconds(response, "X-Ratelimit-Reset")
        if remaining is not None and reset is not None and remaining <= 2:
            log.info("rate limit nearly exhausted, pausing", extra={"sleep_seconds": reset + 1})
            self._sleep(reset + 1)
