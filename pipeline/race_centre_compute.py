"""Pure compute functions for the Race Centre snapshot sections."""

from collections import Counter
from datetime import datetime, timedelta

from .briefing_compute import _driver_info, _numeric_gap, parse_deleted_laps

# ---- starting_grid ----


def compute_starting_grid(qualifying_result: list, race_control: list, drivers: dict) -> list[dict]:
    penalty_notes: dict[str, list[str]] = {}
    for rc in race_control:
        message = (rc.get("message") or "")
        if "PENALTY" in message.upper() or "GRID" in message.upper():
            drv = rc.get("driver_number")
            if drv is not None:
                acronym = _driver_info(drivers, drv)["driver"]
                penalty_notes.setdefault(acronym, []).append(message)

    rows = []
    for r in qualifying_result:
        rows.append(
            {
                "position": r["position"],
                "driver": r["driver"],
                "team": r["team"],
                "team_colour": r["team_colour"],
                "penalty_notes": penalty_notes.get(r["driver"], []),
            }
        )
    return rows


# ---- strategy_forecast ----


def compute_strategy_forecast(last_year_replay_race) -> dict:
    if last_year_replay_race is None or not last_year_replay_race.stints:
        return {
            "stop_distribution": {},
            "typical_pit_laps": [],
            "median_stint_length_by_compound": {},
        }

    stints_by_driver: dict[int, list[dict]] = {}
    for s in last_year_replay_race.stints:
        stints_by_driver.setdefault(s["driver_number"], []).append(s)

    stop_counts = Counter(max(len(v) - 1, 0) for v in stints_by_driver.values())
    total_drivers = len(stints_by_driver) or 1
    stop_distribution = {str(k): round(v / total_drivers, 3) for k, v in stop_counts.items()}

    pit_laps = [
        s["lap_start"]
        for stints in stints_by_driver.values()
        for s in stints[1:]
        if s.get("lap_start") is not None
    ]

    stint_lengths_by_compound: dict[str, list[int]] = {}
    for stints in stints_by_driver.values():
        for s in stints:
            if s.get("lap_start") is None or s.get("lap_end") is None:
                continue
            length = s["lap_end"] - s["lap_start"] + 1
            stint_lengths_by_compound.setdefault(s.get("compound", "UNKNOWN"), []).append(length)

    median_by_compound = {}
    for compound, lengths in stint_lengths_by_compound.items():
        lengths.sort()
        median_by_compound[compound] = lengths[len(lengths) // 2]

    return {
        "stop_distribution": stop_distribution,
        "typical_pit_laps": sorted(pit_laps),
        "median_stint_length_by_compound": median_by_compound,
    }


# ---- race_result ----


def compute_race_result(
    race_session_result: list, qualifying_result: list, drivers: dict
) -> list[dict]:
    driver_to_grid = {r["driver"]: r["position"] for r in qualifying_result}

    rows = []
    for r in race_session_result:
        info = _driver_info(drivers, r["driver_number"])
        grid_position = driver_to_grid.get(info["driver"])
        position = r.get("position")
        positions_gained = (
            grid_position - position if grid_position is not None and position is not None else None
        )
        status = "finished"
        if r.get("dsq"):
            status = "DSQ"
        elif r.get("dnf"):
            status = "DNF"
        rows.append(
            {
                "position": position,
                "driver": info["driver"],
                "team": info["team"],
                "team_colour": info["team_colour"],
                "grid_position": grid_position,
                "positions_gained": positions_gained,
                "status": status,
                "points": r.get("points"),
            }
        )
    rows.sort(key=lambda r: (r["position"] is None, r["position"] or 0))
    return rows


# ---- gaps ----


def compute_gaps(laps: list, intervals: list, drivers: dict) -> list[dict]:
    intervals_sorted = sorted(intervals, key=lambda i: i["date"])

    def gap_at(driver_number: int, at_time: str):
        best = None
        for i in intervals_sorted:
            if i["driver_number"] != driver_number:
                continue
            if i["date"] > at_time:
                break
            best = i
        return best

    rows = []
    for lap in laps:
        start = lap.get("date_start")
        duration = lap.get("lap_duration")
        if start is None or duration is None:
            continue
        lap_end = (datetime.fromisoformat(start) + timedelta(seconds=duration)).isoformat()
        driver_number = lap["driver_number"]
        reading = gap_at(driver_number, lap_end)
        info = _driver_info(drivers, driver_number)
        gap_seconds = None
        laps_down = None
        if reading is not None:
            raw = reading.get("gap_to_leader")
            numeric = _numeric_gap(raw)
            if numeric is not None:
                gap_seconds = numeric
            elif isinstance(raw, str) and "LAP" in raw.upper():
                digits = "".join(c for c in raw if c.isdigit())
                laps_down = int(digits) if digits else None
        rows.append(
            {
                "lap": lap.get("lap_number"),
                "driver": info["driver"],
                "gap_to_leader_seconds": gap_seconds,
                "laps_down": laps_down,
            }
        )
    rows.sort(key=lambda r: (r["lap"] or 0, r["driver"]))
    return rows


# ---- pit_stop_ranking ----


def compute_pit_stop_ranking(pit: list, drivers: dict) -> list[dict]:
    rows = []
    for p in pit:
        info = _driver_info(drivers, p["driver_number"])
        duration = p.get("pit_duration") or p.get("lane_duration")
        if duration is None:
            continue
        rows.append(
            {
                "driver": info["driver"],
                "team_colour": info["team_colour"],
                "lap": p.get("lap_number"),
                "duration": duration,
            }
        )
    rows.sort(key=lambda r: r["duration"])
    return rows


# ---- degradation ----


def compute_degradation(laps: list, stints: list, race_control: list) -> list[dict]:
    deleted = parse_deleted_laps(race_control)
    sc_laps = {
        rc["lap_number"]
        for rc in race_control
        if rc.get("category") == "SafetyCar" and rc.get("lap_number") is not None
    }

    stints_by_driver: dict[int, list[dict]] = {}
    for s in stints:
        stints_by_driver.setdefault(s["driver_number"], []).append(s)

    rows = []
    for lap in laps:
        duration = lap.get("lap_duration")
        driver_number = lap["driver_number"]
        lap_number = lap.get("lap_number")
        if duration is None or lap_number is None:
            continue
        if (driver_number, round(duration, 3)) in deleted:
            continue
        if lap_number in sc_laps:
            continue
        if lap.get("is_pit_out_lap"):
            continue

        stint = next(
            (
                s
                for s in stints_by_driver.get(driver_number, [])
                if s.get("lap_start") is not None
                and s.get("lap_end") is not None
                and s["lap_start"] <= lap_number <= s["lap_end"]
            ),
            None,
        )
        if stint is None:
            continue
        tyre_age = lap_number - stint["lap_start"] + stint.get("tyre_age_at_start", 0)
        rows.append(
            {
                "driver_number": driver_number,
                "compound": stint.get("compound"),
                "tyre_age": tyre_age,
                "lap_time_seconds": duration,
            }
        )
    return rows


# ---- key_moments ----


def compute_key_moments(race_control: list) -> list[dict]:
    rows = []
    for rc in race_control:
        message = (rc.get("message") or "").upper()
        is_moment = (
            rc.get("category") == "SafetyCar"
            or rc.get("flag") == "RED"
            or "PENALTY" in message
            or "RETIRE" in message
            or "DNF" in message
        )
        if not is_moment:
            continue
        rows.append(
            {
                "lap": rc.get("lap_number"),
                "timestamp": rc.get("date"),
                "message": rc.get("message"),
            }
        )
    rows.sort(key=lambda r: r["timestamp"] or "")
    return rows


# ---- team_radio ----


def compute_team_radio(
    team_radio: list, key_moments: list, drivers: dict, max_items: int = 15
) -> list[dict]:
    moment_times = [
        datetime.fromisoformat(m["timestamp"]) for m in key_moments if m.get("timestamp")
    ]

    rows = []
    for tr in team_radio:
        ts = tr.get("date")
        if ts is None:
            continue
        ts_dt = datetime.fromisoformat(ts)
        near_moment = any(abs((ts_dt - mt).total_seconds()) <= 2 * 90 for mt in moment_times)
        if not near_moment:
            continue
        info = _driver_info(drivers, tr.get("driver_number"))
        rows.append(
            {
                "driver": info["driver"],
                "team_colour": info["team_colour"],
                "timestamp": ts,
                "recording_url": tr.get("recording_url"),
            }
        )
    rows.sort(key=lambda r: r["timestamp"])
    return rows[:max_items]
