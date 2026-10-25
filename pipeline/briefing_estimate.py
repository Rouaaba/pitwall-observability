"""Estimates OpenF1 request cost for a backfill run, so the user can see
roughly how long it'll take at the free-tier rate limit before committing
to it. This is necessarily approximate: the response cache means a lot of
requests (e.g. a shared circuit-history meeting lookup) get reused across
meetings in the same season, so the real count is usually lower than this
estimate, never higher.
"""

from dataclasses import dataclass

from .openf1_client import RateLimiter

# Conservative per-meeting request count: meeting + sessions + drivers +
# laps + weather + race_session_result + standings search (~3 candidates)
# + 3 history years x (meetings + sessions + session_result + race_control
# + pit + drivers). Real runs are usually cheaper due to the response
# cache (e.g. a season's /meetings list is fetched once, not once per
# history year), so this is a ceiling, not an average.
ESTIMATED_REQUESTS_PER_MEETING = 1 + 1 + 1 + 1 + 1 + 1 + 3 + 3 * 6


@dataclass
class BackfillEstimate:
    meeting_count: int
    estimated_requests: int
    estimated_seconds: float

    @property
    def estimated_minutes(self) -> float:
        return self.estimated_seconds / 60


def estimate_backfill(
    meeting_count: int, rate_limiter: RateLimiter | None = None
) -> BackfillEstimate:
    limiter = rate_limiter or RateLimiter()
    estimated_requests = meeting_count * ESTIMATED_REQUESTS_PER_MEETING
    # Sustained throughput is bound by the 30/min bucket once the 3/s burst
    # is exhausted, which happens almost immediately for any real backfill.
    requests_per_minute = limiter.per_minute.capacity
    estimated_seconds = (estimated_requests / requests_per_minute) * 60
    return BackfillEstimate(
        meeting_count=meeting_count,
        estimated_requests=estimated_requests,
        estimated_seconds=estimated_seconds,
    )


def format_estimate(estimate: BackfillEstimate) -> str:
    return (
        f"Backfill plan: {estimate.meeting_count} meeting(s), "
        f"~{estimate.estimated_requests} OpenF1 requests, "
        f"~{estimate.estimated_minutes:.1f} minute(s) at the free-tier rate limit "
        f"(actual time is usually lower thanks to response caching)."
    )
