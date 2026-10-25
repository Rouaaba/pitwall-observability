
import pytest
import requests

from pipeline.openf1_client import (
    OpenF1Client,
    OpenF1Error,
    RateLimiter,
    ResponseCache,
    TokenBucket,
)


class FakeClock:
    """Scripted 'now' that only advances when explicitly told to, so tests
    don't depend on real wall-clock time."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---- TokenBucket ----


def test_token_bucket_allows_burst_up_to_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, period_seconds=1.0, now_fn=clock, sleep_fn=lambda s: None)
    for _ in range(3):
        assert bucket.acquire() == 0.0


def test_token_bucket_blocks_when_exhausted():
    clock = FakeClock()
    slept = []
    bucket = TokenBucket(
        capacity=1, period_seconds=1.0, now_fn=clock, sleep_fn=lambda s: slept.append(s)
    )
    bucket.acquire()
    bucket.acquire()
    assert len(slept) == 1
    assert slept[0] > 0


def test_token_bucket_refills_over_time():
    clock = FakeClock()
    bucket = TokenBucket(capacity=1, period_seconds=1.0, now_fn=clock, sleep_fn=lambda s: None)
    bucket.acquire()
    clock.advance(1.0)
    assert bucket.acquire() == 0.0


def test_token_bucket_tracks_total_wait_time():
    clock = FakeClock()

    def fake_sleep(seconds):
        clock.advance(seconds)

    bucket = TokenBucket(capacity=1, period_seconds=1.0, now_fn=clock, sleep_fn=fake_sleep)
    bucket.acquire()
    bucket.acquire()
    assert bucket.wait_seconds_total > 0


def test_rate_limiter_enforces_both_buckets():
    clock = FakeClock()
    waits = []

    def fake_sleep(seconds):
        waits.append(seconds)
        clock.advance(seconds)

    limiter = RateLimiter(
        per_second=TokenBucket(3, 1.0, now_fn=clock, sleep_fn=fake_sleep),
        per_minute=TokenBucket(30, 60.0, now_fn=clock, sleep_fn=fake_sleep),
    )
    for _ in range(3):
        limiter.acquire()
    # 4th request within the same second must wait on the per-second bucket
    limiter.acquire()
    assert len(waits) == 1


# ---- ResponseCache ----


def test_cache_miss_returns_none(tmp_path):
    cache = ResponseCache(tmp_path)
    assert cache.get("laps", {"session_key": 1}) is None


def test_cache_hit_returns_cached_data(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.set("laps", {"session_key": 1}, [{"lap": 1}], permanent=True)
    assert cache.get("laps", {"session_key": 1}) == [{"lap": 1}]


def test_cache_never_stores_latest_requests(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.set("sessions", {"session_key": "latest"}, [{"a": 1}], permanent=True)
    assert cache.get("sessions", {"session_key": "latest"}) is None


def test_cache_never_stores_latest_requests_case_insensitive(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.set("sessions", {"meeting_key": "Latest"}, [{"a": 1}], permanent=True)
    assert cache.get("sessions", {"meeting_key": "Latest"}) is None


def test_cache_never_stores_empty_responses(tmp_path):
    cache = ResponseCache(tmp_path)
    cache.set("intervals", {"session_key": 1}, [], permanent=True)
    assert cache.get("intervals", {"session_key": 1}) is None


def test_permanent_cache_survives_past_short_ttl(tmp_path):
    clock = FakeClock()
    cache = ResponseCache(tmp_path, now_fn=clock)
    cache.set("laps", {"session_key": 1}, [{"lap": 1}], permanent=True)
    clock.advance(10 * 60)  # well past the 5-minute short TTL
    assert cache.get("laps", {"session_key": 1}) == [{"lap": 1}]


def test_non_permanent_cache_expires_after_short_ttl(tmp_path):
    clock = FakeClock()
    cache = ResponseCache(tmp_path, now_fn=clock)
    cache.set("laps", {"session_key": 1}, [{"lap": 1}], permanent=False)
    clock.advance(10 * 60)
    assert cache.get("laps", {"session_key": 1}) is None


def test_non_permanent_cache_valid_within_short_ttl(tmp_path):
    clock = FakeClock()
    cache = ResponseCache(tmp_path, now_fn=clock)
    cache.set("laps", {"session_key": 1}, [{"lap": 1}], permanent=False)
    clock.advance(60)  # within the 5-minute short TTL
    assert cache.get("laps", {"session_key": 1}) == [{"lap": 1}]


# ---- OpenF1Client: retries, timeouts, cache integration ----


class FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else []

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(tmp_path, responses, sleep_calls=None, on_response=None):
    session = FakeSession(responses)
    client = OpenF1Client(
        cache_dir=tmp_path,
        session=session,
        sleep_fn=(sleep_calls.append if sleep_calls is not None else lambda s: None),
        on_response=on_response,
    )
    return client, session


def test_successful_request_is_cached_and_returned(tmp_path):
    client, session = make_client(tmp_path, [FakeResponse(200, [{"lap": 1}])])
    data = client.get("laps", {"session_key": 1}, permanent=True)
    assert data == [{"lap": 1}]
    assert len(session.calls) == 1

    # second call should hit the cache, not the network
    data2 = client.get("laps", {"session_key": 1}, permanent=True)
    assert data2 == [{"lap": 1}]
    assert len(session.calls) == 1


def test_retries_on_429_then_succeeds(tmp_path):
    sleeps = []
    client, session = make_client(
        tmp_path,
        [FakeResponse(429), FakeResponse(200, [{"lap": 1}])],
        sleep_calls=sleeps,
    )
    data = client.get("laps", {"session_key": 1}, permanent=True)
    assert data == [{"lap": 1}]
    assert len(session.calls) == 2
    assert client.stats.retries_total == 1


def test_retries_on_500_then_succeeds(tmp_path):
    client, session = make_client(
        tmp_path, [FakeResponse(500), FakeResponse(200, [{"lap": 1}])]
    )
    data = client.get("laps", {"session_key": 1}, permanent=True)
    assert data == [{"lap": 1}]


def test_retries_on_timeout(tmp_path):
    client, session = make_client(
        tmp_path,
        [requests.exceptions.Timeout("timed out"), FakeResponse(200, [{"lap": 1}])],
    )
    data = client.get("laps", {"session_key": 1}, permanent=True)
    assert data == [{"lap": 1}]


def test_retries_on_connection_error(tmp_path):
    client, session = make_client(
        tmp_path,
        [requests.exceptions.ConnectionError("refused"), FakeResponse(200, [{"lap": 1}])],
    )
    data = client.get("laps", {"session_key": 1}, permanent=True)
    assert data == [{"lap": 1}]


def test_404_returns_empty_list_without_retry(tmp_path):
    client, session = make_client(tmp_path, [FakeResponse(404)])
    data = client.get("intervals", {"session_key": 1}, permanent=True)
    assert data == []
    assert len(session.calls) == 1


def test_exhausting_retries_raises(tmp_path):
    responses = [FakeResponse(500)] * 10  # more than MAX_RETRIES + 1
    client, session = make_client(tmp_path, responses)
    with pytest.raises(OpenF1Error):
        client.get("laps", {"session_key": 1}, permanent=True)


def test_latest_request_is_never_cached(tmp_path):
    client, session = make_client(
        tmp_path,
        [FakeResponse(200, [{"a": 1}]), FakeResponse(200, [{"a": 2}])],
    )
    first = client.get("sessions", {"session_key": "latest"}, permanent=True)
    second = client.get("sessions", {"session_key": "latest"}, permanent=True)
    assert first == [{"a": 1}]
    assert second == [{"a": 2}]
    assert len(session.calls) == 2  # never served from cache


def test_request_stats_start_at_zero(tmp_path):
    client = OpenF1Client(cache_dir=tmp_path)
    assert client.stats.rate_limit_waits_total == 0
    assert client.stats.retries_total == 0


def test_on_response_hook_fires_with_status_code(tmp_path):
    seen = []
    client, session = make_client(
        tmp_path, [FakeResponse(200, [{"lap": 1}])], on_response=seen.append
    )
    client.get("laps", {"session_key": 1}, permanent=True)
    assert seen == [200]


def test_on_response_hook_fires_for_each_retry_attempt(tmp_path):
    seen = []
    client, session = make_client(
        tmp_path,
        [FakeResponse(429), FakeResponse(200, [{"lap": 1}])],
        on_response=seen.append,
    )
    client.get("laps", {"session_key": 1}, permanent=True)
    assert seen == [429, 200]


def test_on_response_hook_fires_with_zero_on_connection_error(tmp_path):
    seen = []
    client, session = make_client(
        tmp_path,
        [requests.exceptions.ConnectionError("refused"), FakeResponse(200, [{"lap": 1}])],
        on_response=seen.append,
    )
    client.get("laps", {"session_key": 1}, permanent=True)
    assert seen == [0, 200]


def test_on_response_hook_not_called_on_cache_hit(tmp_path):
    seen = []
    client, session = make_client(
        tmp_path, [FakeResponse(200, [{"lap": 1}])], on_response=seen.append
    )
    client.get("laps", {"session_key": 1}, permanent=True)
    client.get("laps", {"session_key": 1}, permanent=True)  # cache hit
    assert seen == [200]
