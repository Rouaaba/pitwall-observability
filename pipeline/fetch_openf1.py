"""Fetches and caches raw OpenF1 data for one session, filtered by session_key.

Usage: .venv/bin/python -m pipeline.fetch_openf1 --year 2023 --meeting "Qatar"
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .openf1_client import OpenF1Client

ENDPOINTS = [
    "sessions",
    "drivers",
    "laps",
    "stints",
    "pit",
    "race_control",
    "intervals",
    "position",
    "team_radio",
]
# OpenF1 rejects session_key-only requests for these high-frequency endpoints
# (too many rows); they must be fetched one driver at a time.
PER_DRIVER_ENDPOINTS = ["car_data", "location"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def find_session(client: OpenF1Client, year: int, meeting: str, session_name: str = "Race") -> dict:
    # A past season's session list is final; the current season's keeps
    # growing as new sessions are added, so only cache past seasons forever.
    permanent = year < datetime.now(UTC).year
    sessions = client.get("sessions", {"year": year}, permanent=permanent)
    matches = [
        s
        for s in sessions
        if meeting.lower() in s.get("meeting_key", s.get("location", "")).__str__().lower()
        or meeting.lower() in s.get("country_name", "").lower()
        or meeting.lower() in s.get("location", "").lower()
    ]
    matches = [s for s in matches if s.get("session_name") == session_name] or matches
    if not matches:
        raise SystemExit(f"No session found for year={year} meeting={meeting!r}")
    return matches[0]


def _session_has_ended(session: dict) -> bool:
    date_end = session.get("date_end")
    if not date_end:
        return False
    return datetime.fromisoformat(date_end) < datetime.now(UTC)


def fetch_and_cache(
    client: OpenF1Client, session_key: int, endpoints: list[str] = ENDPOINTS
) -> None:
    out_dir = DATA_DIR / str(session_key)
    out_dir.mkdir(parents=True, exist_ok=True)

    sessions_file = out_dir / "sessions.json"
    if sessions_file.exists():
        session_info = json.loads(sessions_file.read_text())[0]
    else:
        session_data = client.get("sessions", {"session_key": session_key}, permanent=False)
        sessions_file.write_text(json.dumps(session_data, indent=2))
        print(f"[saved] {len(session_data)} records -> {sessions_file}")
        session_info = session_data[0] if session_data else {}

    permanent = _session_has_ended(session_info)

    for endpoint in endpoints:
        out_file = out_dir / f"{endpoint}.json"
        if out_file.exists():
            print(f"[skip] {endpoint} already cached at {out_file}")
            continue
        if endpoint == "sessions":
            continue  # already written above

        print(f"[fetch] {endpoint} for session_key={session_key}")
        data = client.get(endpoint, {"session_key": session_key}, permanent=permanent)
        out_file.write_text(json.dumps(data, indent=2))
        print(f"[saved] {len(data)} records -> {out_file}")

    driver_numbers = json.loads((out_dir / "drivers.json").read_text())
    driver_numbers = sorted({d["driver_number"] for d in driver_numbers})

    for endpoint in PER_DRIVER_ENDPOINTS:
        driver_dir = out_dir / endpoint
        driver_dir.mkdir(exist_ok=True)
        for driver_number in driver_numbers:
            out_file = driver_dir / f"{driver_number}.json"
            if out_file.exists():
                print(f"[skip] {endpoint}/{driver_number} already cached")
                continue
            print(f"[fetch] {endpoint} for driver={driver_number}")
            data = client.get(
                endpoint,
                {"session_key": session_key, "driver_number": driver_number},
                permanent=permanent,
            )
            out_file.write_text(json.dumps(data, indent=2))
            print(f"[saved] {len(data)} records -> {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--meeting", type=str, default="Qatar")
    parser.add_argument("--session-name", type=str, default="Race")
    parser.add_argument(
        "--session-key", type=int, default=None, help="Skip lookup, use this session_key directly"
    )
    args = parser.parse_args()

    client = OpenF1Client()

    if args.session_key:
        session_key = args.session_key
    else:
        session = find_session(client, args.year, args.meeting, args.session_name)
        session_key = session["session_key"]
        print(
            f"Resolved session: {session.get('meeting_key')} {session.get('session_name')} "
            f"-> session_key={session_key}"
        )

    fetch_and_cache(client, session_key)


if __name__ == "__main__":
    main()
