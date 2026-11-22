"""HTTP client with polite delays, retries with backoff and request statistics."""

import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass
class Stats:
    requests: int = 0
    retries: int = 0
    rate_limited: int = 0
    failures: int = 0


class HttpClient:
    def __init__(
        self,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 30.0,
        timeout: float = 25.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout = timeout
        self.stats = Stats()
        self._sleep = sleep

    def pause(self, bounds: Sequence[float]) -> None:
        """Sleep for a random number of seconds between bounds[0] and bounds[1]."""
        self._sleep(random.uniform(bounds[0], bounds[1]))

    def get(self, url: str, params: dict | None = None) -> requests.Response | None:
        """GET with retries. Returns None when the request finally fails."""
        for attempt in range(self.max_retries + 1):
            self.stats.requests += 1
            retry_after = None
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("request error: %s (%s)", url, exc)
            else:
                if response.status_code < 400:
                    return response
                if response.status_code == 429:
                    self.stats.rate_limited += 1
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if response.status_code not in RETRY_STATUSES:
                    log.warning("HTTP %s: %s", response.status_code, url)
                    self.stats.failures += 1
                    return None

            if attempt < self.max_retries:
                delay = max(self.backoff_seconds * 2**attempt, retry_after or 0)
                self.stats.retries += 1
                log.info("retry %d/%d in %.0fs: %s", attempt + 1, self.max_retries, delay, url)
                self._sleep(delay)

        log.error("giving up after %d attempts: %s", self.max_retries + 1, url)
        self.stats.failures += 1
        return None


def _parse_retry_after(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None
