import json
from pathlib import Path

from pipeline.briefing_compute import (
    compute_qualifying_result,
    compute_session_pace,
    parse_deleted_laps,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "austin_2026_qualifying.json").read_text()
)
DRIVERS = {d["driver_number"]: d for d in FIXTURE["drivers"]}
SESSIONS = [{"session_key": 11392, "session_name": "Qualifying", "date_start": "2026-10-24T20:00:00+00:00"}]


def test_parse_deleted_laps_finds_real_deletions():
    deleted = parse_deleted_laps(FIXTURE["race_control"])
    assert len(deleted) > 0


def test_qualifying_result_matches_official_top_8():
    result = compute_qualifying_result(FIXTURE["session_result"], DRIVERS)
    top8 = [r["driver"] for r in result[:8]]
    assert top8 == ["ANT", "VER", "HAD", "LEC", "HAM", "RUS", "PIA", "NOR"]


def test_session_pace_excludes_deleted_laps_for_norris():
    deleted = parse_deleted_laps(FIXTURE["race_control"])
    pace = compute_session_pace(SESSIONS, FIXTURE["laps"], DRIVERS, deleted)
    nor = next(r for r in pace if r["driver"] == "NOR")
    assert nor["best_lap_seconds"] != 94.379
    assert round(nor["best_lap_seconds"], 3) == 94.539
