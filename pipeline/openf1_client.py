"""Shared OpenF1 API client: rate limiting, retry with backoff, and a local
response cache. One client is meant to back every OpenF1-calling path in the
project (fetch_openf1.py today; a future Briefing/Debrief use it too).

Free-tier limits: 3 requests/second, 30 requests/minute. See
docs/ARCHITECTURE.md for why the rate limit shapes the whole "fetch once,
replay/process from a local cache" design, and for the known limitation that
this limiter is per-process only.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

OPENF1_BASE = "https://api.openf1.org/v1"

# "latest" keywords mean something different every time they're queried, so
# a response for them must never be cached.
LATEST_PARAM_VALUES = {"latest"}

SHORT_TTL_SECONDS = 5 * 60

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


def utc_now() -> float:
    return time.time()


@dataclass
class TokenBucket:
    """A single token bucket: `capacity` tokens refilling at `capacity / period_seconds`
    per second. acquire() blocks (sleeps) until a token is available, rather
    than raising, since this client is for batch fetching, not a
    fail-fast service."""

    capacity: float
    period_seconds: float
    now_fn: Callable[[], float] = utc_now
    sleep_fn: Callable[[float], None] = time.sleep
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    wait_seconds_total: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last_refill = self.now_fn()

    @property
    def _refill_rate(self) -> float:
        return self.capacity / self.period_seconds

    def _refill(self) -> None:
        now = self.now_fn()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def acquire(self) -> float:
        """Blocks until one token is available. Returns seconds waited."""
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return 0.0

        deficit = 1 - self._tokens
        wait = deficit / self._refill_rate
        self.sleep_fn(wait)
        self._refill()
        self._tokens = max(0.0, self._tokens - 1)
        self.wait_seconds_total += wait
        return wait


@dataclass
class RateLimiter:
    """Both the 3/s burst and 30/min sustained OpenF1 free-tier limits must
    be satisfied for every request."""

    per_second: TokenBucket = field(default_factory=lambda: TokenBucket(3, 1.0))
    per_minute: TokenBucket = field(default_factory=lambda: TokenBucket(30, 60.0))

    def acquire(self) -> float:
        waited = self.per_second.acquire()
        waited += self.per_minute.acquire()
        return waited

    @property
    def wait_seconds_total(self) -> float:
        return self.per_second.wait_seconds_total + self.per_minute.wait_seconds_total


def _is_latest_request(params: dict) -> bool:
    return any(str(v).lower() in LATEST_PARAM_VALUES for v in params.values())


def _cache_key(endpoint: str, params: dict) -> str:
    normalized = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


@dataclass
class ResponseCache:
    """Raw-response cache keyed by (endpoint, params), independent of
    fetch_openf1.py's own data/<session_key>/<endpoint>.json output files.

    Rules (do not relax without re-reading docs/ARCHITECTURE.md):
      - never cache a "latest"-keyword request (its meaning changes every call)
      - never cache an empty response (data may not be published yet)
      - cache permanently only when the caller says the session has ended;
        otherwise a short TTL, since data can still change
    """

    cache_dir: Path
    now_fn: Callable[[], float] = utc_now

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, endpoint: str, params: dict) -> Path:
        return self.cache_dir / f"{_cache_key(endpoint, params)}.json"

    def get(self, endpoint: str, params: dict) -> list | None:
        if _is_latest_request(params):
            return None
        path = self._path(endpoint, params)
        if not path.exists():
            return None
        envelope = json.loads(path.read_text())
        if not envelope.get("permanent", False):
            if self.now_fn() - envelope["cached_at"] > SHORT_TTL_SECONDS:
                return None
        return envelope["data"]

    def set(self, endpoint: str, params: dict, data: list, permanent: bool) -> None:
        if _is_latest_request(params):
            return
        if not data:
            return
        path = self._path(endpoint, params)
        envelope = {
            "endpoint": endpoint,
            "params": params,
            "cached_at": self.now_fn(),
            "permanent": permanent,
            "data": data,
        }
        path.write_text(json.dumps(envelope))


class OpenF1Error(Exception):
    pass


@dataclass
class RequestStats:
    """Observability hook: lets a caller (e.g. a future pitwall_rate_limit_waits_total
    metric) see rate-limit waits and retry counts without needing to refactor
    the client."""

    rate_limit_waits_total: int = 0
    rate_limit_wait_seconds_total: float = 0.0
    retries_total: int = 0


class OpenF1Client:
    def __init__(
        self,
        base_url: str = OPENF1_BASE,
        cache_dir: Path | None = None,
        rate_limiter: RateLimiter | None = None,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        on_response: Callable[[int], None] | None = None,
        on_rate_limit_wait: Callable[[float], None] | None = None,
    ) -> None:
        self.base_url = base_url
        self.cache = ResponseCache(cache_dir or Path("data/.http_cache"))
        self.rate_limiter = rate_limiter or RateLimiter()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.sleep_fn = sleep_fn
        self.stats = RequestStats()
        # Observability hooks, so a caller can emit pitwall_* metrics
        # without the client needing to know about OTel. on_response is
        # called with the HTTP status code on every real request attempt
        # (not cache hits; 0 on a connection error/timeout).
        # on_rate_limit_wait is called with the seconds waited, each time a
        # request had to wait on the rate limiter.
        self.on_response = on_response
        self.on_rate_limit_wait = on_rate_limit_wait

    def get(self, endpoint: str, params: dict, *, permanent: bool = False) -> list:
        """Fetches one OpenF1 endpoint, honoring the cache rules above.
        `permanent=True` tells the cache this is for a session that has
        already ended, so a non-empty response can be cached forever."""
        cached = self.cache.get(endpoint, params)
        if cached is not None:
            return cached

        data = self._get_with_retry(endpoint, params)
        self.cache.set(endpoint, params, data, permanent=permanent)
        return data

    def _get_with_retry(self, endpoint: str, params: dict) -> list:
        url = f"{self.base_url}/{endpoint}"
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            waited = self.rate_limiter.acquire()
            if waited > 0:
                self.stats.rate_limit_waits_total += 1
                self.stats.rate_limit_wait_seconds_total += waited
                if self.on_rate_limit_wait is not None:
                    self.on_rate_limit_wait(waited)

            try:
                resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if self.on_response is not None:
                    self.on_response(0)
                last_error = exc
                self._backoff_or_raise(attempt, endpoint, exc)
                continue

            if self.on_response is not None:
                self.on_response(resp.status_code)

            if resp.status_code == 404:
                return []

            if resp.status_code in RETRYABLE_STATUS_CODES:
                last_error = OpenF1Error(f"{resp.status_code} from {url}")
                self._backoff_or_raise(attempt, endpoint, last_error)
                continue

            resp.raise_for_status()
            return resp.json()

        raise OpenF1Error(
            f"Exhausted {MAX_RETRIES} retries fetching {endpoint}: {last_error}"
        ) from last_error

    def _backoff_or_raise(self, attempt: int, endpoint: str, error: Exception) -> None:
        if attempt >= MAX_RETRIES:
            return
        self.stats.retries_total += 1
        backoff = min(BASE_BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS)
        logger.warning(
            "Retrying %s after error (attempt %d/%d, backoff %.1fs): %s",
            endpoint, attempt + 1, MAX_RETRIES, backoff, error,
        )
        self.sleep_fn(backoff)
