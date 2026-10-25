"""Fetches everything a briefing snapshot needs for one meeting, via the
shared rate-limited OpenF1 client. Returns raw OpenF1 records (joined to
driver info where convenient); no file I/O, no snapshot shaping — that's
briefing_compute.py.
"""

from dataclasses import dataclass, field
from datetime import datetime

from .openf1_client import OpenF1Client

MIN_HISTORICAL_YEAR = 2023
HISTORY_YEARS_BACK = 3


def _parse(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _session_has_ended(session: dict, now: datetime) -> bool:
    date_end = session.get("date_end")
    return bool(date_end) and _parse(date_end) < now


@dataclass
class YearData:
    year: int
    status: str  # "ok" | "no_race" | "no_data"
    meeting: dict | None = None
    race_session: dict | None = None
    session_result: list = field(default_factory=list)
    race_control: list = field(default_factory=list)
    pit: list = field(default_factory=list)
    drivers: dict[int, dict] = field(default_factory=dict)  # driver_number -> record


@dataclass
class MeetingData:
    meeting: dict
    sessions: list
    drivers: dict[int, dict]  # driver_number -> record, for this meeting
    laps: list
    weather: list  # for the latest completed session
    weather_session_key: int | None
    standings: list  # championship_drivers for the last race before this meeting
    standings_session_key: int | None
    race_session_result: list  # this meeting's own Race session_result, used for finality
    history: list[YearData]  # up to HISTORY_YEARS_BACK prior years, same circuit


def _driver_lookup(client: OpenF1Client, meeting_key: int, *, permanent: bool) -> dict[int, dict]:
    drivers = client.get("drivers", {"meeting_key": meeting_key}, permanent=permanent)
    return {d["driver_number"]: d for d in drivers}


def _find_race_session(sessions: list) -> dict | None:
    for s in sessions:
        if s.get("session_name") == "Race":
            return s
    return None


def _latest_completed_session(sessions: list, now: datetime) -> dict | None:
    ended = [s for s in sessions if _session_has_ended(s, now)]
    if not ended:
        return None
    return max(ended, key=lambda s: s["date_start"])


def fetch_history_year(
    client: OpenF1Client, circuit_key: int, year: int, now: datetime
) -> YearData:
    if year < MIN_HISTORICAL_YEAR:
        return YearData(year=year, status="no_data")

    permanent = year < now.year  # a past season's meetings are final
    meetings = client.get("meetings", {"year": year}, permanent=permanent)
    matches = [m for m in meetings if m.get("circuit_key") == circuit_key]
    if not matches:
        return YearData(year=year, status="no_race")
    meeting = matches[0]

    sessions = client.get(
        "sessions", {"meeting_key": meeting["meeting_key"]}, permanent=permanent
    )
    race_session = _find_race_session(sessions)
    if race_session is None or not _session_has_ended(race_session, now):
        return YearData(year=year, status="no_race", meeting=meeting)

    session_key = race_session["session_key"]
    session_result = client.get("session_result", {"session_key": session_key}, permanent=True)
    race_control = client.get("race_control", {"session_key": session_key}, permanent=True)
    pit = client.get("pit", {"session_key": session_key}, permanent=True)
    drivers = _driver_lookup(client, meeting["meeting_key"], permanent=True)

    return YearData(
        year=year,
        status="ok",
        meeting=meeting,
        race_session=race_session,
        session_result=session_result,
        race_control=race_control,
        pit=pit,
        drivers=drivers,
    )


def fetch_meeting_data(client: OpenF1Client, meeting_key: int, now: datetime) -> MeetingData:
    meetings = client.get("meetings", {"meeting_key": meeting_key}, permanent=False)
    if not meetings:
        raise ValueError(f"No meeting found for meeting_key={meeting_key}")
    meeting = meetings[0]
    meeting_year = meeting["year"]
    meeting_ended = bool(meeting.get("date_end")) and _parse(meeting["date_end"]) < now

    sessions = client.get(
        "sessions", {"meeting_key": meeting_key}, permanent=meeting_ended
    )
    drivers = _driver_lookup(client, meeting_key, permanent=meeting_ended)
    laps = client.get("laps", {"meeting_key": meeting_key}, permanent=meeting_ended)

    latest_session = _latest_completed_session(sessions, now)
    weather: list = []
    weather_session_key = None
    if latest_session is not None:
        weather_session_key = latest_session["session_key"]
        weather = client.get(
            "weather", {"session_key": weather_session_key}, permanent=meeting_ended
        )

    standings, standings_session_key = _fetch_standings_before(client, meeting, now)

    race_session = _find_race_session(sessions)
    race_session_result: list = []
    if race_session is not None and _session_has_ended(race_session, now):
        race_session_result = client.get(
            "session_result",
            {"session_key": race_session["session_key"]},
            permanent=meeting_ended,
        )

    history = [
        fetch_history_year(client, meeting["circuit_key"], meeting_year - offset, now)
        for offset in range(1, HISTORY_YEARS_BACK + 1)
    ]

    return MeetingData(
        meeting=meeting,
        sessions=sessions,
        drivers=drivers,
        laps=laps,
        weather=weather,
        weather_session_key=weather_session_key,
        standings=standings,
        standings_session_key=standings_session_key,
        race_session_result=race_session_result,
        history=history,
    )


def _fetch_standings_before(
    client: OpenF1Client, meeting: dict, now: datetime
) -> tuple[list, int | None]:
    """The championship as of the last completed Race session strictly
    before this meeting's own start, i.e. the pre-race view."""
    year = meeting["year"]
    meeting_start = _parse(meeting["date_start"])
    permanent = year < now.year

    meetings = client.get("meetings", {"year": year}, permanent=permanent)
    candidates = [
        m
        for m in meetings
        if m.get("date_start") and _parse(m["date_start"]) < meeting_start
    ]
    candidates.sort(key=lambda m: m["date_start"], reverse=True)

    for candidate in candidates:
        sessions = client.get(
            "sessions", {"meeting_key": candidate["meeting_key"]}, permanent=True
        )
        race_session = _find_race_session(sessions)
        if race_session is None or not _session_has_ended(race_session, now):
            continue
        session_key = race_session["session_key"]
        standings = client.get("championship_drivers", {"session_key": session_key}, permanent=True)
        if standings:
            return standings, session_key

    return [], None
