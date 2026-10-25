"""Resolves `--meeting latest` to an actual meeting_key.

"Latest" is a pre-race-view concept, not "most recently started": during a
race weekend it must point at the weekend in progress, and between race
weekends it must point at the NEXT Grand Prix, not the previous one --
otherwise Friday/Saturday of a weekend (before the Race session itself has
started) would show last weekend's briefing instead of this one's.
"""

from datetime import datetime

from .openf1_client import OpenF1Client

# Testing meetings (e.g. "Pre-Season Testing") have no Race session and no
# championship relevance; the briefing only covers real Grand Prix weekends.


def _is_race_weekend(meeting: dict, sessions_by_meeting: dict[int, list]) -> bool:
    sessions = sessions_by_meeting.get(meeting["meeting_key"], [])
    return any(s.get("session_name") == "Race" for s in sessions)


def _in_progress(meeting: dict, now: datetime) -> bool:
    start = meeting.get("date_start")
    end = meeting.get("date_end")
    if not start or not end:
        return False
    return datetime.fromisoformat(start) <= now <= datetime.fromisoformat(end)


def resolve_latest_meeting_key(client: OpenF1Client, now: datetime) -> int:
    meetings = client.get("meetings", {"year": now.year}, permanent=False)
    meetings = [m for m in meetings if m.get("date_start")]
    meetings.sort(key=lambda m: m["date_start"])

    in_progress = [m for m in meetings if _in_progress(m, now)]
    if in_progress:
        candidate = _pick_race_weekend(client, in_progress, now)
        if candidate is not None:
            return candidate["meeting_key"]

    upcoming = [m for m in meetings if datetime.fromisoformat(m["date_start"]) > now]
    candidate = _pick_race_weekend(client, upcoming, now)
    if candidate is not None:
        return candidate["meeting_key"]

    # No upcoming race weekend left this year (end of season): fall back to
    # the most recently completed one.
    past = [m for m in meetings if datetime.fromisoformat(m["date_start"]) <= now]
    candidate = _pick_race_weekend(client, list(reversed(past)), now)
    if candidate is not None:
        return candidate["meeting_key"]

    raise ValueError(f"No race weekend found for year={now.year}")


def _pick_race_weekend(client: OpenF1Client, meetings: list, now: datetime) -> dict | None:
    for meeting in meetings:
        permanent = meeting["year"] < now.year
        sessions = client.get(
            "sessions", {"meeting_key": meeting["meeting_key"]}, permanent=permanent
        )
        if any(s.get("session_name") == "Race" for s in sessions):
            return meeting
    return None
