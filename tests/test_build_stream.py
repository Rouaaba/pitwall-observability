import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from replay.events import build_event_stream

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


def iso(seconds_offset: int) -> str:
    return (T0 + timedelta(seconds=seconds_offset)).isoformat()


def write_session(tmp_path: Path) -> Path:
    session_dir = tmp_path / "9999"
    session_dir.mkdir()
    (session_dir / "car_data").mkdir()
    (session_dir / "location").mkdir()

    (session_dir / "sessions.json").write_text(json.dumps([{"date_start": T0.isoformat()}]))
    (session_dir / "drivers.json").write_text(json.dumps([{"driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing"}]))
    (session_dir / "laps.json").write_text(json.dumps([
        {"driver_number": 1, "lap_number": 1, "date_start": iso(20), "lap_duration": 91.0,
         "duration_sector_1": 30.0, "duration_sector_2": 31.0, "duration_sector_3": 30.0},
    ]))
    (session_dir / "stints.json").write_text(json.dumps([]))
    (session_dir / "pit.json").write_text(json.dumps([
        {"driver_number": 1, "date": iso(5), "pit_duration": 22.1},
    ]))
    (session_dir / "race_control.json").write_text(json.dumps([
        {"driver_number": None, "date": iso(0), "message": "GREEN LIGHT"},
    ]))
    (session_dir / "intervals.json").write_text(json.dumps([
        {"driver_number": 1, "date": iso(10), "gap_to_leader": 0.0, "interval": 0.0},
    ]))
    (session_dir / "position.json").write_text(json.dumps([
        {"driver_number": 1, "date": iso(15), "position": 1},
    ]))
    (session_dir / "car_data" / "1.json").write_text(json.dumps([
        {"driver_number": 1, "date": iso(1), "speed": 280, "throttle": 100, "brake": 0, "n_gear": 7},
    ]))
    (session_dir / "location" / "1.json").write_text(json.dumps([
        {"driver_number": 1, "date": iso(2), "x": 100, "y": 200, "z": 0},
    ]))
    return session_dir


def test_build_event_stream_is_time_ordered(tmp_path):
    session_dir = write_session(tmp_path)
    events = list(build_event_stream(session_dir))
    times = [e.event_time for e in events]
    assert times == sorted(times)


def test_build_event_stream_includes_every_source(tmp_path):
    session_dir = write_session(tmp_path)
    events = list(build_event_stream(session_dir))
    kinds = {e.kind.name for e in events}
    assert kinds == {"LAP", "PIT", "RACE_CONTROL", "INTERVAL", "POSITION", "CAR_DATA", "LOCATION"}
