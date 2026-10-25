from pipeline.race_centre_compute import (
    compute_gaps,
    compute_key_moments,
    compute_pit_stop_ranking,
    compute_race_result,
    compute_starting_grid,
    compute_team_radio,
)

DRIVERS = {1: {"driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing", "team_colour": "3671C6"}}
QUALI_RESULT = [{"position": 1, "driver": "VER", "team": "Red Bull Racing", "team_colour": "#3671C6", "q_times": [90.0]}]


def test_starting_grid_includes_penalty_notes():
    rc = [{"driver_number": 1, "message": "5 SECOND TIME PENALTY - GRID"}]
    grid = compute_starting_grid(QUALI_RESULT, rc, DRIVERS)
    assert grid[0]["position"] == 1
    assert grid[0]["penalty_notes"] == ["5 SECOND TIME PENALTY - GRID"]


def test_race_result_computes_positions_gained_and_status():
    session_result = [{"driver_number": 1, "position": 3, "dnf": False, "dsq": False, "points": 15.0}]
    result = compute_race_result(session_result, QUALI_RESULT, DRIVERS)
    assert result[0]["positions_gained"] == -2  # started P1, finished P3
    assert result[0]["status"] == "finished"


def test_race_result_marks_dnf():
    session_result = [{"driver_number": 1, "position": None, "dnf": True, "dsq": False, "points": 0.0}]
    result = compute_race_result(session_result, QUALI_RESULT, DRIVERS)
    assert result[0]["status"] == "DNF"


def test_gaps_parses_numeric_and_lapped():
    laps = [{"driver_number": 1, "lap_number": 1, "date_start": "2026-10-25T20:00:00+00:00", "lap_duration": 90.0}]
    intervals = [{"driver_number": 1, "date": "2026-10-25T20:01:30+00:00", "gap_to_leader": 5.2}]
    rows = compute_gaps(laps, intervals, DRIVERS)
    assert rows[0]["gap_to_leader_seconds"] == 5.2
    assert rows[0]["laps_down"] is None


def test_pit_stop_ranking_sorted_fastest_first():
    pit = [{"driver_number": 1, "lap_number": 10, "pit_duration": 25.0}]
    ranking = compute_pit_stop_ranking(pit, DRIVERS)
    assert ranking[0]["duration"] == 25.0


def test_key_moments_includes_safety_car():
    rc = [{"category": "SafetyCar", "lap_number": 3, "date": "x", "message": "SAFETY CAR DEPLOYED"}]
    moments = compute_key_moments(rc)
    assert len(moments) == 1


def test_team_radio_filters_by_proximity_to_key_moment():
    moments = [{"timestamp": "2026-10-25T20:00:00+00:00"}]
    radio = [
        {"driver_number": 1, "date": "2026-10-25T20:00:30+00:00", "recording_url": "x"},
        {"driver_number": 1, "date": "2026-10-25T21:00:00+00:00", "recording_url": "y"},
    ]
    rows = compute_team_radio(radio, moments, DRIVERS)
    assert len(rows) == 1
    assert rows[0]["recording_url"] == "x"
