"""Pure functions turning fetched OpenF1 data into the snapshot's JSON
sections. No network, no file I/O — everything here is testable with plain
dicts/lists, which is the point: these are the computations the spec cares
about getting right (risk counts, podium joins, pace sorting).
"""

import re
from datetime import datetime, timedelta

from .briefing_fetch import MeetingData, YearData

DEFAULT_FINAL_GRACE_PERIOD = timedelta(hours=24)

# e.g. "CAR 10 (GAS) TIME 1:36.764 DELETED - TRACK LIMITS AT TURN 9 LAP 3 16:07:14"
_DELETED_LAP_RE = re.compile(
    r"CAR\s+(?P<driver_number>\d+)\s*\([^)]*\)\s*TIME\s+(?P<time>[\d:.]+)\s+DELETED"
)


def _parse_lap_time_to_seconds(text: str) -> float | None:
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError:
        return None


def parse_deleted_laps(race_control: list) -> set[tuple[int, float]]:
    """Returns a set of (driver_number, lap_time_seconds) for every lap
    OpenF1's race control messages report as deleted (e.g. track limits).
    OpenF1's /laps endpoint still includes these, so every pace
    calculation must exclude them explicitly."""
    deleted = set()
    for rc in race_control:
        message = rc.get("message") or ""
        m = _DELETED_LAP_RE.search(message)
        if not m:
            continue
        seconds = _parse_lap_time_to_seconds(m.group("time"))
        if seconds is None:
            continue
        deleted.add((int(m.group("driver_number")), round(seconds, 3)))
    return deleted


def _hex_colour(value: str | None) -> str | None:
    if not value:
        return None
    return value if value.startswith("#") else f"#{value}"


def _driver_info(drivers: dict[int, dict], driver_number: int) -> dict:
    d = drivers.get(driver_number)
    if d is None:
        return {"driver": str(driver_number), "team": "unknown", "team_colour": None}
    return {
        "driver": d["name_acronym"],
        "team": d["team_name"],
        "team_colour": _hex_colour(d.get("team_colour")),
    }


def _numeric_gap(value) -> float | None:
    """session_result/intervals gap_to_leader is sometimes a float, sometimes
    the string "+1 LAP", sometimes None (DNF)."""
    if isinstance(value, (int, float)):
        return float(value)
    return None


# ---- meeting ----


def compute_meeting_section(data: MeetingData, now: datetime) -> dict:
    meeting = data.meeting
    return {
        "name": meeting["meeting_name"],
        "circuit": meeting.get("circuit_short_name"),
        "country": meeting.get("country_name"),
        "race_start": _race_start(data.sessions),
        "next_session": compute_next_session(data.sessions, now),
    }


def _race_start(sessions: list) -> str | None:
    for s in sessions:
        if s.get("session_name") == "Race":
            return s.get("date_start")
    return None


def compute_next_session(sessions: list, now: datetime) -> dict | None:
    upcoming = [
        s for s in sessions if s.get("date_start") and datetime.fromisoformat(s["date_start"]) > now
    ]
    if not upcoming:
        return None
    nxt = min(upcoming, key=lambda s: s["date_start"])
    return {"name": nxt["session_name"], "start": nxt["date_start"]}


# ---- risk_by_year ----


def _count_safety_cars(race_control: list) -> tuple[int, int]:
    safety_cars = 0
    virtual_safety_cars = 0
    for rc in race_control:
        if rc.get("category") != "SafetyCar":
            continue
        message = (rc.get("message") or "").upper()
        if "DEPLOYED" not in message:
            continue  # only count deployments, not "ENDING"/"IN THIS LAP" etc.
        if "VIRTUAL" in message:
            virtual_safety_cars += 1
        else:
            safety_cars += 1
    return safety_cars, virtual_safety_cars


def _count_red_flags(race_control: list) -> int:
    return sum(1 for rc in race_control if rc.get("flag") == "RED")


def compute_risk_by_year(history: list[YearData]) -> list[dict]:
    rows = []
    for yd in history:
        if yd.status != "ok":
            rows.append({"year": yd.year, "status": yd.status})
            continue
        safety_cars, vsc = _count_safety_cars(yd.race_control)
        red_flags = _count_red_flags(yd.race_control)
        rows.append(
            {
                "year": yd.year,
                "status": "ok",
                "safety_cars": safety_cars,
                "virtual_safety_cars": vsc,
                "red_flags": red_flags,
            }
        )
    return rows


# ---- podiums ----


def compute_podiums(history: list[YearData]) -> list[dict]:
    rows = []
    for yd in history:
        if yd.status != "ok":
            rows.append({"year": yd.year, "status": yd.status})
            continue
        by_position = {
            r["position"]: r for r in yd.session_result if r.get("position") in (1, 2, 3)
        }
        row = {"year": yd.year, "status": "ok"}
        for pos, key in ((1, "p1"), (2, "p2"), (3, "p3")):
            result = by_position.get(pos)
            if result is None:
                row[key] = None
            else:
                info = _driver_info(yd.drivers, result["driver_number"])
                row[key] = {
                    "driver": info["driver"],
                    "team": info["team"],
                    "team_colour": info["team_colour"],
                }
        rows.append(row)
    return rows


# ---- pit_stops_last_year ----


def compute_pit_stops_last_year(history: list[YearData]) -> list[dict]:
    """The most recent of the fetched history years (history[0], since
    briefing_fetch builds it as year-1, year-2, year-3 in order)."""
    if not history or history[0].status != "ok":
        return []
    yd = history[0]
    counts: dict[int, int] = {}
    for p in yd.pit:
        counts[p["driver_number"]] = counts.get(p["driver_number"], 0) + 1

    rows = []
    for driver_number, stops in counts.items():
        info = _driver_info(yd.drivers, driver_number)
        rows.append(
            {
                "driver": info["driver"],
                "team": info["team"],
                "team_colour": info["team_colour"],
                "stops": stops,
            }
        )
    rows.sort(key=lambda r: r["stops"], reverse=True)
    return rows


# ---- session_pace ----


def compute_session_pace(
    sessions: list,
    laps: list,
    drivers: dict[int, dict],
    deleted_laps: set[tuple[int, float]] | None = None,
    qualifying_order: list[str] | None = None,
) -> list[dict]:
    """Best VALID lap per driver per session -- a pace view, not a ranking.
    Deleted laps (track limits etc.) are excluded. Sorted by official
    qualifying position once qualifying has run (qualifying_order, a list
    of driver acronyms in finishing order), otherwise by the latest
    session."""
    deleted_laps = deleted_laps or set()
    completed_sessions = {s["session_key"]: s for s in sessions}
    best_by_driver_session: dict[tuple[int, int], float] = {}
    for lap in laps:
        duration = lap.get("lap_duration")
        if duration is None:
            continue
        if (lap["driver_number"], round(duration, 3)) in deleted_laps:
            continue
        key = (lap["driver_number"], lap.get("session_key"))
        if key not in best_by_driver_session or duration < best_by_driver_session[key]:
            best_by_driver_session[key] = duration

    rows = []
    for (driver_number, session_key), best_lap in best_by_driver_session.items():
        session = completed_sessions.get(session_key)
        if session is None:
            continue
        info = _driver_info(drivers, driver_number)
        rows.append(
            {
                "driver": info["driver"],
                "team": info["team"],
                "team_colour": info["team_colour"],
                "session": session["session_name"],
                "session_start": session["date_start"],
                "best_lap_seconds": best_lap,
            }
        )

    if qualifying_order:
        order_index = {driver: i for i, driver in enumerate(qualifying_order)}
        rows.sort(key=lambda r: order_index.get(r["driver"], len(order_index)))
    else:
        rows.sort(key=lambda r: r["session_start"], reverse=True)
    return rows


# ---- qualifying_result ----


def compute_qualifying_result(session_result: list, drivers: dict[int, dict]) -> list[dict]:
    """The official qualifying order from /session_result -- ranked by
    segment (Q1/Q2/Q3 knockout), not recomputed from lap times."""
    rows_raw = sorted(
        (r for r in session_result if r.get("position") is not None),
        key=lambda r: r["position"],
    )
    rows = []
    for r in rows_raw:
        info = _driver_info(drivers, r["driver_number"])
        duration = r.get("duration")
        q_times = duration if isinstance(duration, list) else [duration] if duration else []
        rows.append(
            {
                "position": r["position"],
                "driver": info["driver"],
                "team": info["team"],
                "team_colour": info["team_colour"],
                "q_times": q_times,
            }
        )
    return rows


# ---- sessions ----


def compute_sessions_section(sessions: list, now: datetime) -> list[dict]:
    rows = []
    for s in sorted(sessions, key=lambda s: s["date_start"]):
        date_end = s.get("date_end")
        completed = bool(date_end) and datetime.fromisoformat(date_end) < now
        rows.append(
            {
                "name": s["session_name"],
                "start": s["date_start"],
                "end": date_end,
                "completed": completed,
            }
        )
    return rows


# ---- conditions ----


def compute_conditions(weather: list) -> dict:
    if not weather:
        return {
            "track_temperature": None,
            "air_temperature": None,
            "humidity": None,
            "wind_speed": None,
            "rain": None,
            "series": [],
        }
    latest = max(weather, key=lambda w: w["date"])
    series = sorted(weather, key=lambda w: w["date"])
    return {
        "track_temperature": latest.get("track_temperature"),
        "air_temperature": latest.get("air_temperature"),
        "humidity": latest.get("humidity"),
        "wind_speed": latest.get("wind_speed"),
        "rain": bool(latest.get("rainfall")),
        "series": [
            {
                "date": w["date"],
                "track_temperature": w.get("track_temperature"),
                "air_temperature": w.get("air_temperature"),
                "humidity": w.get("humidity"),
                "wind_speed": w.get("wind_speed"),
                "rainfall": w.get("rainfall"),
            }
            for w in series
        ],
    }


# ---- standings ----


def compute_standings(standings: list, drivers: dict[int, dict]) -> list[dict]:
    rows_raw = sorted(
        (s for s in standings if s.get("position_current") is not None),
        key=lambda s: s["position_current"],
    )
    if not rows_raw:
        return []
    leader_points = rows_raw[0]["points_current"]

    rows = []
    for s in rows_raw:
        info = _driver_info(drivers, s["driver_number"])
        rows.append(
            {
                "position": s["position_current"],
                "driver": info["driver"],
                "team": info["team"],
                "team_colour": info["team_colour"],
                "points": s["points_current"],
                "gap_to_leader": leader_points - s["points_current"],
            }
        )
    return rows


# ---- race_replay ----


def compute_race_replay(replay_race) -> dict:
    """Positions per lap per driver, with per-lap pit/SC/VSC/red-flag flags.
    Position is sampled from /position at each lap's end time (nearest
    reading at or before lap_end)."""
    if replay_race is None:
        return {"year": None, "laps": []}

    drivers = replay_race.drivers
    pit_laps = {(p["driver_number"], p.get("lap_number")) for p in replay_race.pit}

    # Per-lap incident flags, derived from race_control messages' lap_number.
    sc_laps, vsc_laps, red_laps = set(), set(), set()
    for rc in replay_race.race_control:
        lap_number = rc.get("lap_number")
        if lap_number is None:
            continue
        message = (rc.get("message") or "").upper()
        if rc.get("category") == "SafetyCar":
            if "VIRTUAL" in message:
                vsc_laps.add(lap_number)
            elif "DEPLOYED" in message or "SAFETY CAR" in message:
                sc_laps.add(lap_number)
        if rc.get("flag") == "RED":
            red_laps.add(lap_number)

    position_sorted = sorted(replay_race.position, key=lambda p: p["date"])

    def position_at(driver_number: int, at_time: str) -> int | None:
        best = None
        for p in position_sorted:
            if p["driver_number"] != driver_number:
                continue
            if p["date"] > at_time:
                break
            best = p["position"]
        return best

    rows = []
    for lap in replay_race.laps:
        driver_number = lap["driver_number"]
        lap_number = lap.get("lap_number")
        start = lap.get("date_start")
        duration = lap.get("lap_duration")
        if start is None or duration is None:
            continue
        lap_end = (datetime.fromisoformat(start) + timedelta(seconds=duration)).isoformat()
        info = _driver_info(drivers, driver_number)
        rows.append(
            {
                "lap": lap_number,
                "driver": info["driver"],
                "team_colour": info["team_colour"],
                "position": position_at(driver_number, lap_end),
                "pit": (driver_number, lap_number) in pit_laps,
                "safety_car": lap_number in sc_laps,
                "virtual_safety_car": lap_number in vsc_laps,
                "red_flag": lap_number in red_laps,
            }
        )
    rows.sort(key=lambda r: (r["lap"] or 0, r["driver"]))
    return {"year": replay_race.year, "laps": rows}


# ---- tyre_strategy ----


def compute_tyre_strategy(replay_race) -> list[dict]:
    if replay_race is None:
        return []
    pit_by_driver: dict[int, list[dict]] = {}
    for p in replay_race.pit:
        pit_by_driver.setdefault(p["driver_number"], []).append(
            {"lap": p.get("lap_number"), "duration": p.get("pit_duration")}
        )

    rows = []
    for driver_number, stints in _group_by(replay_race.stints, "driver_number").items():
        info = _driver_info(replay_race.drivers, driver_number)
        rows.append(
            {
                "driver": info["driver"],
                "team_colour": info["team_colour"],
                "stints": [
                    {
                        "compound": s.get("compound"),
                        "lap_start": s.get("lap_start"),
                        "lap_end": s.get("lap_end"),
                    }
                    for s in stints
                ],
                "pit_stops": pit_by_driver.get(driver_number, []),
            }
        )
    return rows


def _group_by(records: list, key: str) -> dict:
    grouped: dict = {}
    for r in records:
        grouped.setdefault(r[key], []).append(r)
    return grouped


# ---- qualifying_gaps ----


def compute_qualifying_gaps(qualifying_result: list) -> list[dict]:
    if not qualifying_result:
        return []
    pole_time = None
    for r in qualifying_result:
        if r["q_times"]:
            pole_time = min(t for t in r["q_times"] if t is not None)
            break
    rows = []
    for r in qualifying_result:
        best = min((t for t in r["q_times"] if t is not None), default=None)
        gap = round(best - pole_time, 3) if best is not None and pole_time is not None else None
        rows.append(
            {
                "driver": r["driver"],
                "team_colour": r["team_colour"],
                "position": r["position"],
                "best_time": best,
                "gap_to_pole": gap,
            }
        )
    return rows


# ---- standings_progression ----


def compute_standings_progression(rounds: list[dict], drivers: dict[int, dict]) -> list[dict]:
    """`rounds` is [{round, race_name, standings: [championship_drivers rows]}, ...]."""
    rows = []
    for rnd in rounds:
        for s in rnd["standings"]:
            if s.get("position_current") is None:
                continue
            info = _driver_info(drivers, s["driver_number"])
            rows.append(
                {
                    "round": rnd["round"],
                    "race_name": rnd["race_name"],
                    "driver": info["driver"],
                    "team_colour": info["team_colour"],
                    "points": s["points_current"],
                }
            )
    return rows


# ---- finality ----


def compute_final(
    sessions: list,
    session_result: list,
    now: datetime,
    grace_period: timedelta = DEFAULT_FINAL_GRACE_PERIOD,
) -> bool:
    if not sessions:
        return False
    race_session = _race_session(sessions)
    if race_session is None:
        return False

    all_ended = all(
        s.get("date_end") and datetime.fromisoformat(s["date_end"]) < now for s in sessions
    )
    if not all_ended:
        return False

    if not session_result:
        return False

    race_end = datetime.fromisoformat(race_session["date_end"])
    if now - race_end < grace_period:
        return False

    return True


def _race_session(sessions: list) -> dict | None:
    for s in sessions:
        if s.get("session_name") == "Race":
            return s
    return None
