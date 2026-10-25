from datetime import UTC, datetime, timedelta

from pipeline.clock import ReplayClock

RACE_START = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


class FakeClock:
    """Returns a scripted sequence of 'now' values, repeating the last one once exhausted."""

    def __init__(self, values: list[datetime]) -> None:
        self._values = values
        self._index = 0

    def __call__(self) -> datetime:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


def test_offset_computed_once_at_construction():
    t0 = RACE_START + timedelta(hours=2)
    clock = ReplayClock(race_start=RACE_START, speed=1, now_fn=FakeClock([t0]))
    assert clock.offset == timedelta(hours=2)


def test_scaled_wall_clock_at_speed_1_tracks_real_time():
    t0 = RACE_START
    fake = FakeClock([t0, t0 + timedelta(seconds=10)])
    clock = ReplayClock(race_start=RACE_START, speed=1, now_fn=fake)
    assert clock.scheduled_race_time() == RACE_START + timedelta(seconds=10)


def test_scaled_wall_clock_at_speed_5_runs_5x():
    t0 = RACE_START
    fake = FakeClock([t0, t0 + timedelta(seconds=10)])
    clock = ReplayClock(race_start=RACE_START, speed=5, now_fn=fake)
    assert clock.scheduled_race_time() == RACE_START + timedelta(seconds=50)


def test_scaled_wall_clock_at_speed_60():
    t0 = RACE_START
    fake = FakeClock([t0, t0 + timedelta(seconds=2)])
    clock = ReplayClock(race_start=RACE_START, speed=60, now_fn=fake)
    assert clock.scheduled_race_time() == RACE_START + timedelta(seconds=120)


def test_seconds_until_future_event_is_positive():
    t0 = RACE_START
    fake = FakeClock([t0, t0])
    clock = ReplayClock(race_start=RACE_START, speed=1, now_fn=fake)
    target = RACE_START + timedelta(seconds=30)
    assert clock.seconds_until(target) == 30


def test_seconds_until_past_event_is_non_positive():
    t0 = RACE_START
    fake = FakeClock([t0, t0 + timedelta(seconds=100)])
    clock = ReplayClock(race_start=RACE_START, speed=1, now_fn=fake)
    target = RACE_START + timedelta(seconds=30)
    assert clock.seconds_until(target) <= 0


def test_seconds_until_scales_with_speed():
    t0 = RACE_START
    fake = FakeClock([t0, t0])
    clock = ReplayClock(race_start=RACE_START, speed=10, now_fn=fake)
    target = RACE_START + timedelta(seconds=100)
    # 100 race-seconds away, replay runs 10x -> only 10 real seconds of sleep needed
    assert clock.seconds_until(target) == 10
