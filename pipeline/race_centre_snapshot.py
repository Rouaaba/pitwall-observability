"""Assembles the Race Centre snapshot: pre-race sections once qualifying
has run, post-race sections once the race has data."""

from datetime import datetime

from .briefing_compute import compute_qualifying_result, compute_race_replay, compute_tyre_strategy
from .race_centre_compute import (
    compute_degradation,
    compute_gaps,
    compute_key_moments,
    compute_pit_stop_ranking,
    compute_race_result,
    compute_starting_grid,
    compute_strategy_forecast,
    compute_team_radio,
)
from .race_centre_fetch import RaceCentreData

SCHEMA_VERSION = 1


def build_race_centre_snapshot(data: RaceCentreData, now: datetime) -> dict:
    md = data.meeting_data
    qualifying_result = compute_qualifying_result(md.qualifying_session_result, md.drivers)
    race_has_data = bool(md.race_session_result)
    phase = "post_race" if race_has_data else "pre_race"

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "type": "race_centre",
        "meeting_key": md.meeting["meeting_key"],
        "phase": phase,
        "generated_at": now.isoformat(),
    }

    if qualifying_result:
        snapshot["starting_grid"] = compute_starting_grid(
            qualifying_result, data.race_control_full, md.drivers
        )
        snapshot["strategy_forecast"] = compute_strategy_forecast(data.last_year_replay_race)

    if race_has_data:
        snapshot["race_result"] = compute_race_result(
            md.race_session_result, qualifying_result, md.drivers
        )
        race_laps = md.replay_race.laps if md.replay_race else []
        snapshot["gaps"] = compute_gaps(race_laps, data.intervals, md.drivers)
        snapshot["race_replay"] = compute_race_replay(md.replay_race)
        snapshot["tyre_strategy"] = compute_tyre_strategy(md.replay_race)
        pit = md.replay_race.pit if md.replay_race else []
        snapshot["pit_stop_ranking"] = compute_pit_stop_ranking(pit, md.drivers)
        stints = md.replay_race.stints if md.replay_race else []
        snapshot["degradation"] = compute_degradation(
            md.replay_race.laps if md.replay_race else [], stints, data.race_control_full
        )
        key_moments = compute_key_moments(data.race_control_full)
        snapshot["key_moments"] = key_moments
        snapshot["team_radio"] = compute_team_radio(data.team_radio, key_moments, md.drivers)

    return snapshot
