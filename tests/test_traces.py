from datetime import UTC, datetime

from replay.clock import ReplayClock
from replay.engine import ReplayEngine
from replay.events import Event, EventKind
from tests.test_engine import RecordingLogs, RecordingMetrics, RecordingTraces

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


def make_engine(speed=1000000):
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
    return engine, traces, logs


def test_sector_spans_are_back_to_back_and_sum_to_lap_duration():
    engine, traces, _ = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=1,
        payload={
            "lap_number": 5,
            "lap_duration": 90.0,
            "duration_sector_1": 30.0,
            "duration_sector_2": 30.0,
            "duration_sector_3": 30.0,
        },
    )
    engine.run(iter([event]))

    assert len(traces.lap_spans) == 1
    _, _, lap_start, lap_end, lap_span = traces.lap_spans[0]

    assert len(traces.sector_spans) == 3
    s1 = traces.sector_spans[0]
    s2 = traces.sector_spans[1]
    s3 = traces.sector_spans[2]

    assert s1[3] == lap_start  # sector 1 starts when the lap starts
    assert s1[4] == s2[3]  # sector 1 end == sector 2 start
    assert s2[4] == s3[3]  # sector 2 end == sector 3 start
    assert s3[4] == lap_end  # sector 3 ends when the lap ends


def test_missing_sector_duration_skips_that_sector_span():
    engine, traces, _ = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.LAP,
        driver_number=1,
        payload={
            "lap_number": 1,
            "lap_duration": 60.0,
            "duration_sector_1": None,
            "duration_sector_2": 30.0,
            "duration_sector_3": 30.0,
        },
    )
    engine.run(iter([event]))
    assert len(traces.sector_spans) == 2


def test_pit_stop_span_parented_to_last_known_lap_trace():
    engine, traces, logs = make_engine()
    events = [
        Event(
            event_time=T0,
            kind=EventKind.LAP,
            driver_number=1,
            payload={"lap_number": 1, "lap_duration": 90.0},
        ),
        Event(
            event_time=T0,
            kind=EventKind.PIT,
            driver_number=1,
            payload={"lap_number": 2, "pit_duration": 22.0},
        ),
    ]
    engine.run(iter(events))

    lap_span = traces.lap_spans[0][4]
    assert len(traces.pit_stop_spans) == 1
    parent_context, _, _, _ = traces.pit_stop_spans[0]
    assert parent_context == lap_span.get_span_context()

    assert len(logs.pit_stops) == 1
    _, _, trace_context, _ = logs.pit_stops[0]
    assert trace_context == lap_span.get_span_context()


def test_pit_stop_before_any_lap_has_no_parent():
    engine, traces, logs = make_engine()
    events = [
        Event(
            event_time=T0,
            kind=EventKind.PIT,
            driver_number=1,
            payload={"lap_number": 1, "pit_duration": 22.0},
        ),
    ]
    engine.run(iter(events))

    assert len(traces.pit_stop_spans) == 1
    parent_context, attrs, start_time, end_time = traces.pit_stop_spans[0]
    assert parent_context is None
    assert attrs == {"driver": "VER", "team": "Red Bull Racing"}
    assert start_time < end_time

    _, _, trace_context, _ = logs.pit_stops[0]
    assert trace_context is None


def test_trace_id_propagates_from_lap_to_later_pit_log_line():
    engine, traces, logs = make_engine()
    events = [
        Event(
            event_time=T0,
            kind=EventKind.LAP,
            driver_number=1,
            payload={"lap_number": 1, "lap_duration": 90.0},
        ),
        Event(
            event_time=T0,
            kind=EventKind.PIT,
            driver_number=1,
            payload={"lap_number": 2, "pit_duration": 22.0},
        ),
    ]
    engine.run(iter(events))

    lap_trace_id = traces.lap_spans[0][4].get_span_context().trace_id
    pit_trace_context = logs.pit_stops[0][2]
    assert pit_trace_context.trace_id == lap_trace_id
