"""Assembles one meeting's full snapshot dict from fetched data, and the
content-hash used to decide whether a snapshot actually changed (so publish
doesn't commit on every run just because generated_at always differs)."""

import hashlib
import json
from datetime import datetime, timedelta

from .briefing_compute import (
    DEFAULT_FINAL_GRACE_PERIOD,
    compute_conditions,
    compute_final,
    compute_meeting_section,
    compute_pit_stops_last_year,
    compute_podiums,
    compute_risk_by_year,
    compute_session_pace,
    compute_sessions_section,
    compute_standings,
)
from .briefing_fetch import MeetingData

# Fields that vary on every run even when nothing meaningful changed; these
# are excluded from the content hash used to decide whether to commit.
RUN_SPECIFIC_FIELDS = {"generated_at"}


def build_snapshot(
    data: MeetingData,
    now: datetime,
    grace_period: timedelta = DEFAULT_FINAL_GRACE_PERIOD,
) -> dict:
    source_session_keys = sorted(
        {s["session_key"] for s in data.sessions if s.get("session_key")}
    )

    snapshot = {
        "meeting_key": data.meeting["meeting_key"],
        "meeting": compute_meeting_section(data, now),
        "risk_by_year": compute_risk_by_year(data.history),
        "podiums": compute_podiums(data.history),
        "pit_stops_last_year": compute_pit_stops_last_year(data.history),
        "session_pace": compute_session_pace(data.sessions, data.laps, data.drivers),
        "sessions": compute_sessions_section(data.sessions, now),
        "conditions": compute_conditions(data.weather),
        "standings": compute_standings(data.standings, data.drivers),
        "final": compute_final(data.sessions, data.race_session_result, now, grace_period),
        "generated_at": now.isoformat(),
        "source_session_keys": source_session_keys,
    }
    return snapshot


def content_hash(snapshot: dict) -> str:
    stable = {k: v for k, v in snapshot.items() if k not in RUN_SPECIFIC_FIELDS}
    encoded = json.dumps(stable, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def snapshots_differ(old: dict | None, new: dict) -> bool:
    if old is None:
        return True
    return content_hash(old) != content_hash(new)
