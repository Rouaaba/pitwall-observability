"""Resolves season/race/session into a cached session_key, validating against
what's actually on disk under data/ rather than querying OpenF1 live."""

import json
from dataclasses import dataclass
from pathlib import Path

from .race_labels import normalize_race, normalize_season, normalize_session


@dataclass(frozen=True, slots=True)
class CachedSession:
    session_key: int
    season: str
    race: str
    session: str
    race_name: str  # original, human-readable (e.g. "Qatar")
    session_name: str  # original (e.g. "Race")


class RaceNotFoundError(Exception):
    def __init__(self, season: str, race: str, session: str, cached: list[CachedSession]):
        self.season = season
        self.race = race
        self.session = session
        self.cached = cached
        super().__init__(self._message())

    def _message(self) -> str:
        lines = [
            f"No cached data for season={self.season!r} race={self.race!r} "
            f"session={self.session!r}."
        ]
        if self.cached:
            lines.append("Cached races:")
            for c in self.cached:
                lines.append(
                    f"  - season={c.season} race={c.race} session={c.session} "
                    f"({c.race_name} {c.session_name}, session_key={c.session_key})"
                )
        else:
            lines.append("No races are cached at all.")
        lines.append(
            f"To fetch it: .venv/bin/python replay/fetch_openf1.py "
            f"--year {self.season} --meeting \"{self.race.replace('_', ' ').title()}\""
        )
        return "\n".join(lines)


def _load_cached_sessions(data_dir: Path) -> list[CachedSession]:
    cached = []
    for session_dir in sorted(data_dir.glob("*")):
        sessions_file = session_dir / "sessions.json"
        if not session_dir.is_dir() or not sessions_file.exists():
            continue
        sessions = json.loads(sessions_file.read_text())
        if not sessions:
            continue
        info = sessions[0]
        race_name = info.get("country_name") or info.get("location") or "unknown"
        session_name = info.get("session_name", "unknown")
        cached.append(
            CachedSession(
                session_key=info["session_key"],
                season=normalize_season(info["year"]),
                race=normalize_race(race_name),
                session=normalize_session(session_name),
                race_name=race_name,
                session_name=session_name,
            )
        )
    return cached


def resolve_session_key(data_dir: Path, season: str, race: str, session: str) -> int:
    """season/race/session are matched after normalization, so callers can pass
    either raw OpenF1 names ("Qatar", "Race") or already-normalized values."""
    want_season = normalize_season(season)
    want_race = normalize_race(race)
    want_session = normalize_session(session)

    cached = _load_cached_sessions(data_dir)
    for c in cached:
        if c.season == want_season and c.race == want_race and c.session == want_session:
            return c.session_key

    raise RaceNotFoundError(want_season, want_race, want_session, cached)
