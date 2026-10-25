from datetime import UTC, datetime

from pipeline.events import EventKind, _events_from_records, _synthesize_stint_events

T0 = datetime(2023, 10, 8, 17, 0, 0, tzinfo=UTC)


def iso(seconds_offset: int) -> str:
    from datetime import timedelta

    return (T0 + timedelta(seconds=seconds_offset)).isoformat()


def test_events_from_records_is_time_ordered():
    records = [
        {"date": iso(30), "driver_number": 1},
        {"date": iso(10), "driver_number": 2},
        {"date": iso(20), "driver_number": 3},
    ]
    events = _events_from_records(records, EventKind.PIT, "date")
    times = [e.event_time for e in events]
    assert times == sorted(times)


def test_events_from_records_skips_null_timestamps():
    records = [
        {"date": iso(10), "driver_number": 1},
        {"date": None, "driver_number": 2},
    ]
    events = _events_from_records(records, EventKind.PIT, "date")
    assert len(events) == 1
    assert events[0].driver_number == 1


def test_stint_timestamp_uses_matching_lap_start():
    laps = [
        {"driver_number": 1, "lap_number": 5, "date_start": iso(500)},
    ]
    stints = [
        {"driver_number": 1, "lap_start": 5, "lap_end": 10, "compound": "SOFT", "tyre_age_at_start": 0},
    ]
    events = _synthesize_stint_events(stints, laps, race_start=T0)
    assert len(events) == 1
    assert events[0].event_time == T0.fromisoformat(iso(500))
    assert events[0].kind is EventKind.STINT_START


def test_stint_timestamp_falls_back_to_race_start_when_lap_missing():
    laps = []
    stints = [
        {"driver_number": 1, "lap_start": 1, "lap_end": 10, "compound": "SOFT", "tyre_age_at_start": 0},
    ]
    events = _synthesize_stint_events(stints, laps, race_start=T0)
    assert events[0].event_time == T0


def test_stint_timestamp_falls_back_when_lap_has_no_date_start():
    laps = [
        {"driver_number": 1, "lap_number": 1, "date_start": None},
    ]
    stints = [
        {"driver_number": 1, "lap_start": 1, "lap_end": 10, "compound": "SOFT", "tyre_age_at_start": 0},
    ]
    events = _synthesize_stint_events(stints, laps, race_start=T0)
    assert events[0].event_time == T0
