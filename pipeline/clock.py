"""Maps race time onto a scaled wall clock, so a cached race can be replayed at any speed."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class ReplayClock:
    race_start: datetime
    speed: float
    now_fn: Callable[[], datetime] = utc_now
    start_wall: datetime = field(init=False)

    def __post_init__(self) -> None:
        self.start_wall = self.now_fn()

    @property
    def offset(self) -> timedelta:
        return self.start_wall - self.race_start

    def scheduled_race_time(self) -> datetime:
        elapsed_wall = self.now_fn() - self.start_wall
        return self.race_start + elapsed_wall * self.speed

    def seconds_until(self, target_race_time: datetime) -> float:
        remaining = (target_race_time - self.scheduled_race_time()).total_seconds()
        return remaining / self.speed
