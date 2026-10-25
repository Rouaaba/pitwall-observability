from datetime import UTC, datetime, timedelta

from pipeline.clock import ReplayClock
from pipeline.engine import ReplayEngine
from pipeline.events import Event, EventKind

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


class RecordingMetrics:
    """No-op metrics stub that records calls instead of talking to OTel."""

    def __init__(self) -> None:
        self.lap_times = []
        self.events_processed = []
        self.lags = []
        self.car_positions = []

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

    def record_car_position(self, attrs, x, y):
        self.car_positions.append((attrs, x, y))

    def record_event_processed(self, kind):
        self.events_processed.append(kind)

    def record_lag(self, lag_seconds):
        self.lags.append(lag_seconds)


class FakeSpanContext:
    """Stand-in for an OTel SpanContext: just needs to be a distinguishable value."""

    def __init__(self, trace_id):
        self.trace_id = trace_id

    def __eq__(self, other):
        return isinstance(other, FakeSpanContext) and self.trace_id == other.trace_id


class FakeSpan:
    def __init__(self, trace_id):
        self._context = FakeSpanContext(trace_id)

    def get_span_context(self):
        return self._context


class RecordingTraces:
    """No-op traces stub that records calls instead of talking to OTel."""

    def __init__(self) -> None:
        self.lap_spans = []
        self.sector_spans = []
        self.pit_stop_spans = []
        self._next_trace_id = 0

    def start_lap_span(self, attrs, lap_number, start_time, end_time):
        self._next_trace_id += 1
        span = FakeSpan(self._next_trace_id)
        self.lap_spans.append((attrs, lap_number, start_time, end_time, span))
        return span

    def record_sector_span(self, parent_span, attrs, sector, start_time, end_time):
        self.sector_spans.append((parent_span, attrs, sector, start_time, end_time))

    def record_pit_stop_span(self, parent_span_context, attrs, start_time, end_time):
        self.pit_stop_spans.append((parent_span_context, attrs, start_time, end_time))


class RecordingLogs:
    """No-op logs stub that records calls instead of talking to OTel."""

    def __init__(self) -> None:
        self.race_control = []
        self.pit_stops = []
        self.stint_starts = []
        self.team_radio = []

    def log_race_control(self, attrs, payload, trace_context, emitted_at):
        self.race_control.append((attrs, payload, trace_context, emitted_at))

    def log_pit_stop(self, attrs, payload, trace_context, emitted_at):
        self.pit_stops.append((attrs, payload, trace_context, emitted_at))

    def log_stint_start(self, attrs, payload, emitted_at):
        self.stint_starts.append((attrs, payload, emitted_at))

    def log_team_radio(self, attrs, payload, trace_context, emitted_at):
        self.team_radio.append((attrs, payload, trace_context, emitted_at))


def make_engine(speed=1000000):
    # Very high speed so _wait_until never actually sleeps meaningfully in tests.
    clock = ReplayClock(race_start=T0, speed=speed)
    metrics = RecordingMetrics()
    traces = RecordingTraces()
    logs = RecordingLogs()
    engine = ReplayEngine(
        clock=clock,
        metrics=metrics,
        traces=traces,
        logs=logs,
        driver_labels={1: {"driver": "VER", "team": "Red Bull Racing"}},
    )
    return engine, metrics, traces, logs


def test_dispatch_lap_event_records_lap_time_with_driver_labels():
    engine, metrics, _, _ = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=1,
        payload={"lap_duration": 91.234, "driver_number": 1},
    )
    engine.run(iter([event]))
    assert metrics.lap_times == [({"driver": "VER", "team": "Red Bull Racing"}, 91.234)]


def test_unknown_driver_falls_back_to_driver_number_label():
    engine, metrics, _, _ = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=99,
        payload={"lap_duration": 90.0},
    )
    engine.run(iter([event]))
    attrs, _ = metrics.lap_times[0]
    assert attrs["driver"] == "99"


def test_location_event_records_car_position():
    engine, metrics, _, _ = make_engine()
    events = [
        Event(
            event_time=T0,
            kind=EventKind.LOCATION,
            driver_number=1,
            payload={"x": 100.0, "y": -250.0},
        ),
    ]
    engine.run(iter(events))
    assert metrics.events_processed == ["LOCATION"]
    assert metrics.car_positions == [
        ({"driver": "VER", "team": "Red Bull Racing"}, 100.0, -250.0)
    ]


def test_race_control_event_is_logged():
    engine, metrics, _, logs = make_engine()
    events = [
        Event(
            event_time=T0,
            kind=EventKind.RACE_CONTROL,
            driver_number=None,
            payload={"message": "SAFETY CAR", "flag": None, "category": "SafetyCar"},
        ),
    ]
    engine.run(iter(events))
    assert metrics.events_processed == ["RACE_CONTROL"]
    assert len(logs.race_control) == 1


def test_lag_recorded_for_every_event():
    engine, metrics, _, _ = make_engine()
    events = [
        Event(event_time=T0, kind=EventKind.LOCATION, driver_number=1, payload={}),
        Event(event_time=T0 + timedelta(seconds=1), kind=EventKind.LOCATION, driver_number=1, payload={}),
    ]
    engine.run(iter(events))
    assert len(metrics.lags) == 2
    assert all(lag >= 0 for lag in metrics.lags)
