from pipeline.briefing_compute import (
    compute_qualifying_gaps,
    compute_race_replay,
    compute_standings_progression,
    compute_tyre_strategy,
)
from pipeline.briefing_fetch import RaceReplayData

DRIVERS = {
    1: {"driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing", "team_colour": "3671C6"},
    81: {"driver_number": 81, "name_acronym": "PIA", "team_name": "McLaren", "team_colour": "FF8000"},
}


def test_race_replay_none_when_no_race():
    assert compute_race_replay(None) == {"year": None, "laps": []}


def test_race_replay_flags_pit_and_safety_car():
    replay = RaceReplayData(
        year=2025,
        laps=[{"driver_number": 1, "lap_number": 2, "date_start": "2025-10-19T12:00:00+00:00", "lap_duration": 90.0}],
        position=[{"driver_number": 1, "position": 3, "date": "2025-10-19T12:01:00+00:00"}],
        race_control=[{"category": "SafetyCar", "flag": None, "lap_number": 2, "message": "SAFETY CAR DEPLOYED"}],
        stints=[],
        pit=[{"driver_number": 1, "lap_number": 2}],
        drivers=DRIVERS,
    )
    out = compute_race_replay(replay)
    assert out["year"] == 2025
    row = out["laps"][0]
    assert row == {
        "lap": 2, "driver": "VER", "team_colour": "#3671C6", "position": 3,
        "pit": True, "safety_car": True, "virtual_safety_car": False, "red_flag": False,
    }


def test_tyre_strategy_groups_stints_and_pit_stops():
    replay = RaceReplayData(
        year=2025, laps=[], position=[], race_control=[],
        stints=[{"driver_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 10}],
        pit=[{"driver_number": 1, "lap_number": 10, "pit_duration": 22.1}],
        drivers=DRIVERS,
    )
    out = compute_tyre_strategy(replay)
    assert out == [
        {
            "driver": "VER",
            "team_colour": "#3671C6",
            "stints": [{"compound": "SOFT", "lap_start": 1, "lap_end": 10}],
            "pit_stops": [{"lap": 10, "duration": 22.1}],
        }
    ]


def test_qualifying_gaps_computes_gap_to_pole():
    qualifying_result = [
        {"position": 1, "driver": "VER", "team_colour": "#3671C6", "q_times": [95.0, 94.0, 93.0]},
        {"position": 2, "driver": "PIA", "team_colour": "#FF8000", "q_times": [95.5, 94.5, 93.5]},
    ]
    gaps = compute_qualifying_gaps(qualifying_result)
    assert gaps[0]["gap_to_pole"] == 0
    assert gaps[1]["gap_to_pole"] == 0.5


def test_standings_progression_builds_rows_per_round():
    rounds = [
        {"round": 1, "race_name": "Qatar GP", "standings": [
            {"driver_number": 1, "position_current": 1, "points_current": 25.0},
        ]},
        {"round": 2, "race_name": "Abu Dhabi GP", "standings": [
            {"driver_number": 1, "position_current": 1, "points_current": 50.0},
        ]},
    ]
    rows = compute_standings_progression(rounds, DRIVERS)
    assert [r["points"] for r in rows] == [25.0, 50.0]
    assert rows[0]["race_name"] == "Qatar GP"
