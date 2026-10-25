"""Pure functions turning fetched OpenF1 data into the snapshot's JSON
sections. No network, no file I/O — everything here is testable with plain
dicts/lists, which is the point: these are the computations the spec cares
about getting right (risk counts, podium joins, pace sorting).
"""

from datetime import datetime, timedelta

from .briefing_fetch import MeetingData, YearData

DEFAULT_FINAL_GRACE_PERIOD = timedelta(hours=24)


def _driver_info(drivers: dict[int, dict], driver_number: int) -> dict:
    d = drivers.get(driver_number)
    if d is None:
        return {"driver": str(driver_number), "team": "unknown", "team_colour": None}
    return {
        "driver": d["name_acronym"],
        "team": d["team_name"],
        "team_colour": d.get("team_colour"),
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
                row[key] = _driver_info(yd.drivers, result["driver_number"])["driver"]
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
        rows.append({"driver": info["driver"], "team": info["team"], "stops": stops})
    rows.sort(key=lambda r: r["stops"], reverse=True)
    return rows


# ---- session_pace ----


def compute_session_pace(sessions: list, laps: list, drivers: dict[int, dict]) -> list[dict]:
    completed_sessions = {s["session_key"]: s for s in sessions}
    best_by_driver_session: dict[tuple[int, int], float] = {}
    for lap in laps:
        duration = lap.get("lap_duration")
        if duration is None:
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
                "session": session["session_name"],
                "session_start": session["date_start"],
                "best_lap_seconds": best_lap,
            }
        )
    rows.sort(key=lambda r: r["session_start"], reverse=True)
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
                "points": s["points_current"],
                "gap_to_leader": leader_points - s["points_current"],
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
