"""Fetches the extra data race_centre needs beyond what briefing_fetch
already gets via fetch_meeting_data (reused as-is: sessions, drivers, laps,
race_session_result, qualifying_session_result, replay_race, history)."""

from dataclasses import dataclass, field
from datetime import datetime

from .briefing_fetch import MeetingData, _find_race_session, _session_has_ended
from .openf1_client import OpenF1Client


@dataclass
class RaceCentreData:
    meeting_data: MeetingData
    race_session: dict | None
    race_control_full: list = field(default_factory=list)  # whole race session, not just quali
    intervals: list = field(default_factory=list)
    team_radio: list = field(default_factory=list)
    last_year_replay_race: object = None  # RaceReplayData | None, for strategy_forecast


def fetch_race_centre_data(
    client: OpenF1Client, meeting_data: MeetingData, now: datetime
) -> RaceCentreData:
    sessions = meeting_data.sessions
    race_session = _find_race_session(sessions)
    meeting_ended = bool(meeting_data.meeting.get("date_end"))

    race_control_full: list = []
    intervals: list = []
    team_radio: list = []
    if race_session is not None and _session_has_ended(race_session, now):
        session_key = race_session["session_key"]
        race_control_full = client.get(
            "race_control", {"session_key": session_key}, permanent=meeting_ended
        )
        intervals = client.get(
            "intervals", {"session_key": session_key}, permanent=meeting_ended
        )
        team_radio = client.get(
            "team_radio", {"session_key": session_key}, permanent=meeting_ended
        )

    last_year = meeting_data.history[0] if meeting_data.history else None
    last_year_replay_race = None
    if last_year is not None and last_year.status == "ok" and last_year.race_session is not None:
        from .briefing_fetch import RaceReplayData

        lk = last_year.race_session["session_key"]
        stints = client.get("stints", {"session_key": lk}, permanent=True)
        last_year_replay_race = RaceReplayData(
            year=last_year.year,
            laps=client.get("laps", {"session_key": lk}, permanent=True),
            position=[],
            race_control=last_year.race_control,
            stints=stints,
            pit=last_year.pit,
            drivers=last_year.drivers,
        )

    return RaceCentreData(
        meeting_data=meeting_data,
        race_session=race_session,
        race_control_full=race_control_full,
        intervals=intervals,
        team_radio=team_radio,
        last_year_replay_race=last_year_replay_race,
    )
