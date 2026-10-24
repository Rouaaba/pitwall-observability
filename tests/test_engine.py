from datetime import UTC, datetime, timedelta

from replay.clock import ReplayClock
from replay.engine import ReplayEngine
from replay.events import Event, EventKind

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


class RecordingMetrics:
    """No-op metrics stub that records calls instead of talking to OTel."""

    def __init__(self) -> None:
        self.lap_times = []
        self.events_processed = []
        self.lags = []

    def record_lap_time(self, attrs, lap_time_s):
        self.lap_times.append((attrs, lap_time_s))

    def record_sector_time(self, attrs, sector, duration_s):
        pass

    def record_position(self, attrs, position):
        pass

    def record_gap_to_leader(self, attrs, gap_s):
        pass

    def record_interval(self, attrs, interval_s):
        pass

    def record_tyre_age(self, attrs, compound, age_laps):
        pass

    def record_pit_stop(self, attrs):
        pass

    def record_pit_duration(self, attrs, duration_s):
        pass

    def record_car_telemetry(self, attrs, speed, throttle, brake, n_gear):
        pass

    def record_event_processed(self, kind):
        self.events_processed.append(kind)

    def record_lag(self, lag_seconds):
        self.lags.append(lag_seconds)


def make_engine(speed=1000000):
    # Very high speed so _wait_until never actually sleeps meaningfully in tests.
    clock = ReplayClock(race_start=T0, speed=speed)
    metrics = RecordingMetrics()
    engine = ReplayEngine(clock=clock, metrics=metrics, driver_labels={1: {"driver": "VER", "team": "Red Bull Racing"}})
    return engine, metrics


def test_dispatch_lap_event_records_lap_time_with_driver_labels():
    engine, metrics = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=1,
        payload={"lap_duration": 91.234, "driver_number": 1},
    )
    engine.run(iter([event]))
    assert metrics.lap_times == [({"driver": "VER", "team": "Red Bull Racing"}, 91.234)]


def test_unknown_driver_falls_back_to_driver_number_label():
    engine, metrics = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=99,
        payload={"lap_duration": 90.0},
    )
    engine.run(iter([event]))
    attrs, _ = metrics.lap_times[0]
    assert attrs["driver"] == "99"


def test_location_and_race_control_events_are_counted_but_not_metriced():
    engine, metrics = make_engine()
    events = [
        Event(event_time=T0, kind=EventKind.LOCATION, driver_number=1, payload={}),
        Event(
            event_time=T0 + timedelta(seconds=1),
            kind=EventKind.RACE_CONTROL,
            driver_number=None,
            payload={"message": "SAFETY CAR"},
        ),
    ]
    engine.run(iter(events))
    assert metrics.events_processed == ["LOCATION", "RACE_CONTROL"]
    assert metrics.lap_times == []


def test_lag_recorded_for_every_event():
    engine, metrics = make_engine()
    events = [
        Event(event_time=T0, kind=EventKind.LOCATION, driver_number=1, payload={}),
        Event(event_time=T0 + timedelta(seconds=1), kind=EventKind.LOCATION, driver_number=1, payload={}),
    ]
    engine.run(iter(events))
    assert len(metrics.lags) == 2
    assert all(lag >= 0 for lag in metrics.lags)
