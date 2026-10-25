"""Normalizes season/race/session into the exact label values used across
every pitwall_* metric, log and span, so dashboard variables can match them.

Label contract (must stay stable: dashboards filter on these exact names
and value shapes):
  season:  string year, e.g. "2023"
  race:    lowercase, spaces/punctuation collapsed to underscores, e.g. "qatar", "abu_dhabi"
  session: short code, e.g. "R", "Q", "S", "SQ", "FP1", "FP2", "FP3"
"""

import re

_SESSION_CODES = {
    "race": "R",
    "qualifying": "Q",
    "sprint": "S",
    "sprint qualifying": "SQ",
    "sprint shootout": "SQ",
    "practice 1": "FP1",
    "practice 2": "FP2",
    "practice 3": "FP3",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_season(year: int | str) -> str:
    return str(year)


def normalize_race(name: str) -> str:
    slug = _NON_ALNUM.sub("_", name.strip().lower()).strip("_")
    return slug


def normalize_session(session_name: str) -> str:
    key = session_name.strip().lower()
    return _SESSION_CODES.get(key, _NON_ALNUM.sub("_", key).strip("_").upper())


def race_labels(year: int | str, race_name: str, session_name: str) -> dict[str, str]:
    return {
        "season": normalize_season(year),
        "race": normalize_race(race_name),
        "session": normalize_session(session_name),
    }
