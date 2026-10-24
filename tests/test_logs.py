from datetime import UTC, datetime

from opentelemetry._logs import SeverityNumber

from replay.clock import ReplayClock
from replay.engine import ReplayEngine
from replay.events import Event, EventKind
from replay.logs import severity_for_race_control
from tests.test_engine import RecordingLogs, RecordingMetrics, RecordingTraces

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


def test_severity_red_flag_is_error():
    number, text = severity_for_race_control("RED", "Flag")
    assert number is SeverityNumber.ERROR
    assert text == "ERROR"


def test_severity_safety_car_is_warn():
    number, text = severity_for_race_control(None, "SafetyCar")
    assert number is SeverityNumber.WARN
    assert text == "WARN"


def test_severity_yellow_flag_is_warn():
    number, text = severity_for_race_control("YELLOW", "Flag")
    assert number is SeverityNumber.WARN
    assert text == "WARN"


def test_severity_other_is_info():
    number, text = severity_for_race_control("GREEN", "Other")
    assert number is SeverityNumber.INFO
    assert text == "INFO"

    number, text = severity_for_race_control(None, "Drs")
    assert number is SeverityNumber.INFO


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
    return engine, logs


def test_race_control_with_null_driver_has_no_trace_id():
    engine, logs = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.RACE_CONTROL,
        driver_number=None,
        payload={"message": "GREEN FLAG", "flag": "GREEN", "category": "Flag"},
    )
    engine.run(iter([event]))
    _, _, trace_context, _ = logs.race_control[0]
    assert trace_context is None


def test_pit_stop_log_includes_driver_and_pit_duration():
    engine, logs = make_engine()
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
            payload={"lap_number": 2, "pit_duration": 22.1},
        ),
    ]
    engine.run(iter(events))
    attrs, payload, _, _ = logs.pit_stops[0]
    assert attrs["driver"] == "VER"
    assert attrs["team"] == "Red Bull Racing"
    assert payload["pit_duration"] == 22.1


def test_team_radio_logs_recording_url():
    engine, logs = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.TEAM_RADIO,
        driver_number=1,
        payload={"recording_url": "https://example.com/radio.mp3"},
    )
    engine.run(iter([event]))
    assert len(logs.team_radio) == 1
    attrs, payload, _, _ = logs.team_radio[0]
    assert payload["recording_url"] == "https://example.com/radio.mp3"


def test_stint_start_logs_compound():
    engine, logs = make_engine()
    event = Event(
        event_time=T0,
        kind=EventKind.STINT_START,
        driver_number=1,
        payload={"compound": "SOFT", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 0},
    )
    engine.run(iter([event]))
    assert len(logs.stint_starts) == 1
    attrs, payload, _ = logs.stint_starts[0]
    assert payload["compound"] == "SOFT"
