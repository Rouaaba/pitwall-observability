"""Loads cached OpenF1 session data and builds one time-ordered event stream."""

import heapq
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path


class EventKind(Enum):
    LAP = auto()
    STINT_START = auto()
    PIT = auto()
    RACE_CONTROL = auto()
    INTERVAL = auto()
    POSITION = auto()
    CAR_DATA = auto()
    LOCATION = auto()


@dataclass(frozen=True, slots=True)
class Event:
    event_time: datetime
    kind: EventKind
    driver_number: int | None
    payload: dict


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def get_race_start(session_dir: Path) -> datetime:
    sessions = json.loads((session_dir / "sessions.json").read_text())
    return _parse_time(sessions[0]["date_start"])


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _events_from_records(
    records: list[dict], kind: EventKind, time_field: str
) -> list[Event]:
    events = []
    for record in records:
        raw_time = record.get(time_field)
        if raw_time is None:
            continue
        events.append(
            Event(
                event_time=_parse_time(raw_time),
                kind=kind,
                driver_number=record.get("driver_number"),
                payload=record,
            )
        )
    events.sort(key=lambda e: e.event_time)
    return events


def _synthesize_stint_events(
    stints: list[dict], laps: list[dict], race_start: datetime
) -> list[Event]:
    lap_start_time: dict[tuple[int, int], datetime] = {}
    for lap in laps:
        raw_time = lap.get("date_start")
        if raw_time is None:
            continue
        key = (lap["driver_number"], lap["lap_number"])
        lap_start_time[key] = _parse_time(raw_time)

    events = []
    for stint in stints:
        key = (stint["driver_number"], stint["lap_start"])
        event_time = lap_start_time.get(key, race_start)
        events.append(
            Event(
                event_time=event_time,
                kind=EventKind.STINT_START,
                driver_number=stint["driver_number"],
                payload=stint,
            )
        )
    events.sort(key=lambda e: e.event_time)
    return events


def iter_endpoint_events(session_dir: Path) -> list[Iterator[Event]]:
    """One sorted iterator per data source: per-endpoint files plus per-driver car_data/location."""
    race_start = get_race_start(session_dir)
    laps = _load_json(session_dir / "laps.json")
    stints = _load_json(session_dir / "stints.json")

    sources: list[list[Event]] = [
        _events_from_records(laps, EventKind.LAP, "date_start"),
        _synthesize_stint_events(stints, laps, race_start),
        _events_from_records(_load_json(session_dir / "pit.json"), EventKind.PIT, "date"),
        _events_from_records(
            _load_json(session_dir / "race_control.json"), EventKind.RACE_CONTROL, "date"
        ),
        _events_from_records(
            _load_json(session_dir / "intervals.json"), EventKind.INTERVAL, "date"
        ),
        _events_from_records(
            _load_json(session_dir / "position.json"), EventKind.POSITION, "date"
        ),
    ]

    for car_data_file in sorted((session_dir / "car_data").glob("*.json")):
        records = _load_json(car_data_file)
        sources.append(_events_from_records(records, EventKind.CAR_DATA, "date"))

    for location_file in sorted((session_dir / "location").glob("*.json")):
        records = _load_json(location_file)
        sources.append(_events_from_records(records, EventKind.LOCATION, "date"))

    return [iter(source) for source in sources if source]


def build_event_stream(session_dir: Path) -> Iterator[Event]:
    """Lazily merges every per-source sorted event list into one time-ordered stream."""
    sources = iter_endpoint_events(session_dir)
    return heapq.merge(*sources, key=lambda e: e.event_time)
