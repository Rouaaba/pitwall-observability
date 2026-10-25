"""Fetches and caches raw OpenF1 data for one session, filtered by session_key.

Usage: uv run python replay/fetch_openf1.py --year 2023 --meeting "Qatar"
"""

import argparse
import json
from pathlib import Path

import requests

OPENF1_BASE = "https://api.openf1.org/v1"
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


def find_session(year: int, meeting: str, session_name: str = "Race") -> dict:
    resp = requests.get(f"{OPENF1_BASE}/sessions", params={"year": year}, timeout=30)
    resp.raise_for_status()
    sessions = resp.json()
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


def fetch_and_cache(session_key: int, endpoints: list[str] = ENDPOINTS) -> None:
    out_dir = DATA_DIR / str(session_key)
    out_dir.mkdir(parents=True, exist_ok=True)

    for endpoint in endpoints:
        out_file = out_dir / f"{endpoint}.json"
        if out_file.exists():
            print(f"[skip] {endpoint} already cached at {out_file}")
            continue

        print(f"[fetch] {endpoint} for session_key={session_key}")
        resp = requests.get(
            f"{OPENF1_BASE}/{endpoint}",
            params={"session_key": session_key},
            timeout=60,
        )
        if resp.status_code == 404:
            # Not every endpoint has data for every session type, e.g.
            # qualifying/practice sessions have no intervals (no race gaps).
            print(f"[skip] {endpoint} has no data for session_key={session_key} (404)")
            out_file.write_text("[]")
            continue
        resp.raise_for_status()
        data = resp.json()
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
            resp = requests.get(
                f"{OPENF1_BASE}/{endpoint}",
                params={"session_key": session_key, "driver_number": driver_number},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
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

    if args.session_key:
        session_key = args.session_key
    else:
        session = find_session(args.year, args.meeting, args.session_name)
        session_key = session["session_key"]
        print(
            f"Resolved session: {session.get('meeting_key')} {session.get('session_name')} "
            f"-> session_key={session_key}"
        )

    fetch_and_cache(session_key)


if __name__ == "__main__":
    main()
