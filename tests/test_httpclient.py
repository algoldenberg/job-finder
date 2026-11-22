import pytest
import requests

from job_collector.httpclient import HttpClient


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class FakeSession:
    """Returns the given outcomes in order: an int is a status code, an exception is raised."""

    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.headers: dict = {}
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, FakeResponse):
            return outcome
        return FakeResponse(outcome)


def make_client(outcomes: list) -> tuple[HttpClient, FakeSession, list[float]]:
    sleeps: list[float] = []
    session = FakeSession(outcomes)
    client = HttpClient(session=session, sleep=sleeps.append, backoff_seconds=30)
    return client, session, sleeps


def test_success_on_first_try() -> None:
    client, session, sleeps = make_client([200])
    assert client.get("https://example.com").status_code == 200
    assert (session.calls, sleeps, client.stats.failures) == (1, [], 0)


def test_retries_after_rate_limit() -> None:
    client, session, sleeps = make_client([429, 200])
    assert client.get("https://example.com").status_code == 200
    assert sleeps == [30]
    assert (client.stats.rate_limited, client.stats.retries) == (1, 1)


def test_respects_retry_after_header() -> None:
    client, _, sleeps = make_client([FakeResponse(429, {"Retry-After": "90"}), 200])
    client.get("https://example.com")
    assert sleeps == [90]


def test_no_retry_on_not_found() -> None:
    client, session, sleeps = make_client([404])
    assert client.get("https://example.com") is None
    assert (session.calls, sleeps, client.stats.failures) == (1, [], 1)


def test_gives_up_with_exponential_backoff() -> None:
    client, session, sleeps = make_client([503, 503, 503, 503])
    assert client.get("https://example.com") is None
    assert session.calls == 4
    assert sleeps == [30, 60, 120]
    assert client.stats.failures == 1


def test_retries_after_connection_error() -> None:
    client, _, sleeps = make_client([requests.ConnectionError("boom"), 200])
    assert client.get("https://example.com").status_code == 200
    assert sleeps == [30]


def test_pause_stays_within_bounds() -> None:
    client, _, sleeps = make_client([])
    for _ in range(50):
        client.pause([3, 7])
    assert all(3 <= s <= 7 for s in sleeps)
    assert len(sleeps) == 50


def test_sets_browser_headers() -> None:
    client, session, _ = make_client([])
    assert "Mozilla" in session.headers["User-Agent"]
    assert client.timeout == pytest.approx(25.0)
