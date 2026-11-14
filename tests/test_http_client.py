import pytest
import requests

from src.extract.http_client import ApiError, RetryableHttpError
from tests.conftest import make_response


def test_success_returns_payload(make_client):
    client, session, _ = make_client([make_response(200, {"ok": True})])
    assert client.get_json("https://x.test", {"a": 1}).payload == {"ok": True}
    assert session.calls[0]["timeout"] == 30


def test_retries_5xx_then_succeeds(make_client):
    client, session, sleeps = make_client([make_response(503), make_response(200, {"ok": 1})])
    assert client.get_json("https://x.test").payload == {"ok": 1}
    assert len(session.calls) == 2
    assert len(sleeps) == 1


def test_retries_connection_error(make_client):
    client, session, _ = make_client([requests.ConnectionError("boom"), make_response(200, {})])
    client.get_json("https://x.test")
    assert len(session.calls) == 2


def test_gives_up_after_max_retries(make_client):
    client, session, _ = make_client([make_response(500)] * 3, max_retries=3)
    with pytest.raises(RetryableHttpError):
        client.get_json("https://x.test")
    assert len(session.calls) == 3


def test_4xx_is_not_retried(make_client):
    client, session, _ = make_client([make_response(400, {"reason": "bad date"})])
    with pytest.raises(ApiError) as err:
        client.get_json("https://x.test")
    assert err.value.status == 400
    assert "bad date" in str(err.value)
    assert len(session.calls) == 1


def test_429_waits_for_server_reset(make_client):
    client, _, sleeps = make_client(
        [make_response(429, headers={"X-Ratelimit-Reset": "17"}), make_response(200, {})]
    )
    client.get_json("https://x.test")
    assert sleeps == [18.0]  # reset + 1 second safety margin


def test_pauses_when_quota_nearly_used(make_client):
    client, _, sleeps = make_client(
        [make_response(200, {}, headers={"X-Ratelimit-Remaining": "1", "X-Ratelimit-Reset": "30"})]
    )
    client.get_json("https://x.test")
    assert sleeps == [31.0]


def test_invalid_json_raises_api_error(make_client):
    bad = make_response(200)
    bad._content = b"<html>not json</html>"
    client, _, _ = make_client([bad])
    with pytest.raises(ApiError):
        client.get_json("https://x.test")
