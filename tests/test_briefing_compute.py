from datetime import UTC, datetime

from pipeline.briefing_compute import (
    compute_conditions,
    compute_final,
    compute_next_session,
    compute_pit_stops_last_year,
    compute_podiums,
    compute_risk_by_year,
    compute_session_pace,
    compute_sessions_section,
    compute_standings,
)
from pipeline.briefing_fetch import YearData

DRIVERS = {
    1: {"driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing", "team_colour": "3671C6"},
    81: {"driver_number": 81, "name_acronym": "PIA", "team_name": "McLaren", "team_colour": "FF8000"},
    44: {"driver_number": 44, "name_acronym": "HAM", "team_name": "Ferrari", "team_colour": "E8002D"},
}


# ---- risk_by_year ----


def test_risk_by_year_counts_safety_car_deployments_only_once():
    race_control = [
        {"category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"},  # not a deployment
        {"category": "SafetyCar", "message": "VIRTUAL SAFETY CAR DEPLOYED"},
        {"category": "Flag", "flag": "YELLOW"},
    ]
    history = [YearData(year=2023, status="ok", race_control=race_control)]
    rows = compute_risk_by_year(history)
    assert rows == [
        {"year": 2023, "status": "ok", "safety_cars": 1, "virtual_safety_cars": 1, "red_flags": 0}
    ]


def test_risk_by_year_counts_red_flags():
    race_control = [{"category": "Flag", "flag": "RED"}, {"category": "Flag", "flag": "RED"}]
    history = [YearData(year=2023, status="ok", race_control=race_control)]
    rows = compute_risk_by_year(history)
    assert rows[0]["red_flags"] == 2


def test_risk_by_year_zero_when_no_incidents():
    history = [YearData(year=2023, status="ok", race_control=[])]
    rows = compute_risk_by_year(history)
    assert rows[0]["safety_cars"] == 0
    assert rows[0]["virtual_safety_cars"] == 0
    assert rows[0]["red_flags"] == 0


def test_risk_by_year_distinguishes_no_race_from_no_data():
    history = [
        YearData(year=2024, status="no_race"),
        YearData(year=2022, status="no_data"),
    ]
    rows = compute_risk_by_year(history)
    assert rows == [
        {"year": 2024, "status": "no_race"},
        {"year": 2022, "status": "no_data"},
    ]


# ---- podiums ----


def test_podiums_joins_driver_acronyms():
    session_result = [
        {"position": 1, "driver_number": 1},
        {"position": 2, "driver_number": 81},
        {"position": 3, "driver_number": 44},
    ]
    history = [YearData(year=2023, status="ok", session_result=session_result, drivers=DRIVERS)]
    rows = compute_podiums(history)
    assert rows == [
        {
            "year": 2023,
            "status": "ok",
            "p1": {"driver": "VER", "team": "Red Bull Racing", "team_colour": "#3671C6"},
            "p2": {"driver": "PIA", "team": "McLaren", "team_colour": "#FF8000"},
            "p3": {"driver": "HAM", "team": "Ferrari", "team_colour": "#E8002D"},
        }
    ]


def test_podiums_handles_missing_position():
    # A DNF/DSQ entry has position=None and must not be mistaken for p1/p2/p3.
    session_result = [
        {"position": 1, "driver_number": 1},
        {"position": None, "driver_number": 44},
    ]
    history = [YearData(year=2023, status="ok", session_result=session_result, drivers=DRIVERS)]
    rows = compute_podiums(history)
    assert rows[0]["p1"]["driver"] == "VER"
    assert rows[0]["p2"] is None
    assert rows[0]["p3"] is None


def test_podiums_marks_years_with_no_race():
    history = [YearData(year=2024, status="no_race")]
    rows = compute_podiums(history)
    assert rows == [{"year": 2024, "status": "no_race"}]


def test_podiums_marks_years_outside_openf1_coverage():
    history = [YearData(year=2022, status="no_data")]
    rows = compute_podiums(history)
    assert rows == [{"year": 2022, "status": "no_data"}]


# ---- pit_stops_last_year ----


def test_pit_stops_last_year_counts_and_sorts_descending():
    pit = [
        {"driver_number": 1}, {"driver_number": 1}, {"driver_number": 1},
        {"driver_number": 81}, {"driver_number": 81},
        {"driver_number": 44},
    ]
    history = [YearData(year=2023, status="ok", pit=pit, drivers=DRIVERS)]
    rows = compute_pit_stops_last_year(history)
    assert rows == [
        {"driver": "VER", "team": "Red Bull Racing", "team_colour": "#3671C6", "stops": 3},
        {"driver": "PIA", "team": "McLaren", "team_colour": "#FF8000", "stops": 2},
        {"driver": "HAM", "team": "Ferrari", "team_colour": "#E8002D", "stops": 1},
    ]


def test_pit_stops_last_year_empty_when_no_race():
    history = [YearData(year=2024, status="no_race")]
    assert compute_pit_stops_last_year(history) == []


def test_pit_stops_last_year_uses_most_recent_history_year():
    pit_2023 = [{"driver_number": 1}]
    pit_2022 = [{"driver_number": 81}] * 5
    # briefing_fetch builds history as [year-1, year-2, year-3], so index 0
    # is always the most recent year regardless of status of later entries.
    history = [
        YearData(year=2023, status="ok", pit=pit_2023, drivers=DRIVERS),
        YearData(year=2022, status="no_data", pit=pit_2022, drivers=DRIVERS),
    ]
    rows = compute_pit_stops_last_year(history)
    assert rows == [
        {"driver": "VER", "team": "Red Bull Racing", "team_colour": "#3671C6", "stops": 1}
    ]


# ---- session_pace ----


def test_session_pace_takes_best_lap_per_driver_per_session():
    sessions = [{"session_key": 10, "session_name": "Qualifying", "date_start": "2026-03-13T14:00:00+00:00"}]
    laps = [
        {"driver_number": 1, "session_key": 10, "lap_duration": 91.2},
        {"driver_number": 1, "session_key": 10, "lap_duration": 90.5},  # better
        {"driver_number": 1, "session_key": 10, "lap_duration": None},  # ignored
        {"driver_number": 81, "session_key": 10, "lap_duration": 90.8},
    ]
    rows = compute_session_pace(sessions, laps, DRIVERS)
    by_driver = {r["driver"]: r["best_lap_seconds"] for r in rows}
    assert by_driver == {"VER": 90.5, "PIA": 90.8}
    assert next(r for r in rows if r["driver"] == "VER")["team_colour"] == "#3671C6"


def test_session_pace_sorted_by_latest_session_first():
    sessions = [
        {"session_key": 10, "session_name": "Practice 1", "date_start": "2026-03-13T10:00:00+00:00"},
        {"session_key": 11, "session_name": "Qualifying", "date_start": "2026-03-13T14:00:00+00:00"},
    ]
    laps = [
        {"driver_number": 1, "session_key": 10, "lap_duration": 92.0},
        {"driver_number": 1, "session_key": 11, "lap_duration": 90.0},
    ]
    rows = compute_session_pace(sessions, laps, DRIVERS)
    assert [r["session"] for r in rows] == ["Qualifying", "Practice 1"]


def test_session_pace_ignores_laps_for_unknown_session():
    sessions = [{"session_key": 10, "session_name": "Race", "date_start": "2026-03-13T14:00:00+00:00"}]
    laps = [{"driver_number": 1, "session_key": 999, "lap_duration": 90.0}]
    assert compute_session_pace(sessions, laps, DRIVERS) == []


# ---- sessions ----


def test_sessions_section_marks_completed_by_date_end():
    now = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)
    sessions = [
        {"session_name": "Practice 1", "date_start": "2026-03-13T08:00:00+00:00", "date_end": "2026-03-13T09:00:00+00:00"},
        {"session_name": "Qualifying", "date_start": "2026-03-13T14:00:00+00:00", "date_end": "2026-03-13T15:00:00+00:00"},
    ]
    rows = compute_sessions_section(sessions, now)
    assert rows[0]["completed"] is True
    assert rows[1]["completed"] is False


# ---- conditions ----


def test_conditions_uses_latest_reading():
    weather = [
        {"date": "2026-03-13T08:00:00+00:00", "track_temperature": 30, "air_temperature": 20, "humidity": 50, "wind_speed": 1.0, "rainfall": 0},
        {"date": "2026-03-13T09:00:00+00:00", "track_temperature": 35, "air_temperature": 22, "humidity": 45, "wind_speed": 1.5, "rainfall": 1},
    ]
    conditions = compute_conditions(weather)
    assert conditions["track_temperature"] == 35
    assert conditions["rain"] is True
    assert len(conditions["series"]) == 2
    assert conditions["series"][0]["humidity"] == 50
    assert conditions["series"][0]["wind_speed"] == 1.0
    assert conditions["series"][0]["rainfall"] == 0


def test_conditions_empty_when_no_weather_data():
    conditions = compute_conditions([])
    assert conditions["track_temperature"] is None
    assert conditions["series"] == []


# ---- standings ----


def test_standings_computes_gap_to_leader_from_points():
    standings = [
        {"driver_number": 1, "position_current": 1, "points_current": 433.0},
        {"driver_number": 81, "position_current": 2, "points_current": 400.0},
    ]
    rows = compute_standings(standings, DRIVERS)
    assert rows[0]["gap_to_leader"] == 0
    assert rows[1]["gap_to_leader"] == 33.0
    assert rows[0]["team_colour"] == "#3671C6"


def test_standings_empty_when_no_data():
    assert compute_standings([], DRIVERS) == []


# ---- next_session ----


def test_next_session_picks_earliest_upcoming():
    now = datetime(2026, 3, 13, 9, 0, tzinfo=UTC)
    sessions = [
        {"session_name": "Practice 1", "date_start": "2026-03-13T08:00:00+00:00"},  # past
        {"session_name": "Qualifying", "date_start": "2026-03-13T14:00:00+00:00"},  # soonest future
        {"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00"},
    ]
    result = compute_next_session(sessions, now)
    assert result == {"name": "Qualifying", "start": "2026-03-13T14:00:00+00:00"}


def test_next_session_null_when_all_sessions_past():
    now = datetime(2026, 3, 16, 9, 0, tzinfo=UTC)
    sessions = [{"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00"}]
    assert compute_next_session(sessions, now) is None


# ---- final ----


def test_final_requires_all_sessions_ended():
    now = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    sessions = [
        {"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00", "date_end": "2026-03-15T16:00:00+00:00"},
    ]
    assert compute_final(sessions, session_result=[{"position": 1}], now=now) is False


def test_final_requires_session_result_present():
    now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)  # well past grace period
    sessions = [
        {"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00", "date_end": "2026-03-15T16:00:00+00:00"},
    ]
    assert compute_final(sessions, session_result=[], now=now) is False


def test_final_requires_grace_period_elapsed():
    sessions = [
        {"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00", "date_end": "2026-03-15T16:00:00+00:00"},
    ]
    just_after = datetime(2026, 3, 15, 17, 0, tzinfo=UTC)  # 1 hour after race end
    assert compute_final(sessions, session_result=[{"position": 1}], now=just_after) is False

    well_after = datetime(2026, 3, 16, 17, 0, tzinfo=UTC)  # 25 hours after race end
    assert compute_final(sessions, session_result=[{"position": 1}], now=well_after) is True


def test_final_grace_period_is_configurable():
    from datetime import timedelta

    sessions = [
        {"session_name": "Race", "date_start": "2026-03-15T14:00:00+00:00", "date_end": "2026-03-15T16:00:00+00:00"},
    ]
    one_hour_after = datetime(2026, 3, 15, 17, 0, tzinfo=UTC)
    assert compute_final(
        sessions, session_result=[{"position": 1}], now=one_hour_after,
        grace_period=timedelta(minutes=30),
    ) is True


def test_final_false_with_no_race_session():
    now = datetime(2026, 3, 16, 12, 0, tzinfo=UTC)
    sessions = [
        {"session_name": "Qualifying", "date_start": "2026-03-14T14:00:00+00:00", "date_end": "2026-03-14T15:00:00+00:00"},
    ]
    assert compute_final(sessions, session_result=[{"position": 1}], now=now) is False
