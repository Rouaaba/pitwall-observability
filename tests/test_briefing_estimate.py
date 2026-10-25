from pipeline.briefing_estimate import estimate_backfill, format_estimate
from pipeline.openf1_client import RateLimiter, TokenBucket


def test_estimate_scales_with_meeting_count():
    e1 = estimate_backfill(1)
    e5 = estimate_backfill(5)
    assert e5.estimated_requests == e1.estimated_requests * 5
    assert e5.meeting_count == 5


def test_estimate_duration_respects_per_minute_limit():
    limiter = RateLimiter(
        per_second=TokenBucket(3, 1.0), per_minute=TokenBucket(30, 60.0)
    )
    estimate = estimate_backfill(1, rate_limiter=limiter)
    expected_seconds = (estimate.estimated_requests / 30) * 60
    assert estimate.estimated_seconds == expected_seconds


def test_format_estimate_includes_key_numbers():
    estimate = estimate_backfill(3)
    text = format_estimate(estimate)
    assert "3 meeting" in text
    assert str(estimate.estimated_requests) in text
