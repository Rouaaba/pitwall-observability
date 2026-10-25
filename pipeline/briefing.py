"""CLI entrypoint: generates (and publishes) Briefing snapshots.

    python -m pipeline.briefing --meeting latest
    python -m pipeline.briefing --meeting 1221
    python -m pipeline.briefing --backfill --season 2025
    python -m pipeline.briefing --backfill --season 2025 --yes
    python -m pipeline.briefing --meeting 1221 --force
"""

import argparse
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from .briefing_estimate import estimate_backfill, format_estimate
from .briefing_fetch import fetch_meeting_data
from .briefing_meeting_select import resolve_latest_meeting_key
from .briefing_metrics import build_briefing_meter_provider, create_briefing_metrics
from .briefing_snapshot import build_snapshot
from .openf1_client import OpenF1Client
from .snapshot_publish import (
    commit_and_push,
    rebuild_index,
    snapshot_path,
    write_snapshot,
)

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Pitwall Briefing snapshots.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--meeting", help="Meeting key, or 'latest'")
    group.add_argument("--backfill", action="store_true", help="Generate snapshots for a season")
    parser.add_argument("--season", type=int, help="Required with --backfill")
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if an existing snapshot is final"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the backfill confirmation prompt"
    )
    parser.add_argument(
        "--data-repo",
        type=Path,
        default=None,
        help=(
            "Local checkout of the pitwall-data repo to write snapshots into. "
            "Falls back to $PITWALL_DATA_REPO if not passed. If neither is set, "
            "writes to a local-only directory (./pitwall-briefing-output) and "
            "never attempts to publish -- this deliberately has NO default that "
            "points inside this project's own repo, since that previously "
            "caused snapshot files to be committed into pitwall-observability "
            "by mistake."
        ),
    )
    parser.add_argument(
        "--otlp-endpoint", default=os.environ.get("OTLP_ENDPOINT", "localhost:4317")
    )
    args = parser.parse_args(argv)
    if args.backfill and args.season is None:
        parser.error("--backfill requires --season")

    if args.data_repo is None:
        env_repo = os.environ.get("PITWALL_DATA_REPO")
        args.data_repo = Path(env_repo) if env_repo else Path("pitwall-briefing-output")
        if not env_repo:
            logger.warning(
                "Neither --data-repo nor $PITWALL_DATA_REPO is set; writing local "
                "files only to %s -- publishing is disabled.",
                args.data_repo,
            )

    return args


def generate_one_meeting(
    client: OpenF1Client,
    repo_dir: Path,
    meeting_key: int,
    now: datetime,
    *,
    is_latest: bool,
    force: bool,
    metrics=None,
) -> list[Path]:
    """Returns the paths actually written this call (empty if the snapshot
    was skipped or unchanged)."""
    existing_path = snapshot_path(repo_dir, meeting_key)
    if existing_path.exists() and not force:
        existing = json.loads(existing_path.read_text())
        if existing.get("final"):
            logger.info("[skip] meeting_key=%s already final", meeting_key)
            return []

    start = time.monotonic()
    try:
        data = fetch_meeting_data(client, meeting_key, now)
        snapshot = build_snapshot(data, now)
    except Exception as exc:
        logger.exception("Failed to generate snapshot for meeting_key=%s", meeting_key)
        if metrics is not None:
            metrics.record_snapshot_failure(reason=type(exc).__name__)
        raise

    written = write_snapshot(repo_dir, snapshot, is_latest=is_latest)
    duration = time.monotonic() - start

    if metrics is not None:
        season = str(data.meeting.get("year", ""))
        metrics.record_snapshot_generated(meeting_key, season, now.timestamp())
        metrics.record_snapshot_duration(meeting_key, season, duration)

    logger.info(
        "[%s] meeting_key=%s final=%s duration=%.1fs",
        "changed" if written else "unchanged", meeting_key, snapshot["final"], duration,
    )
    return written


def run_backfill(
    client: OpenF1Client,
    repo_dir: Path,
    season: int,
    now: datetime,
    *,
    force: bool,
    assume_yes: bool,
    metrics=None,
) -> None:
    meetings = client.get("meetings", {"year": season}, permanent=season < now.year)
    race_meetings = []
    for meeting in meetings:
        sessions = client.get(
            "sessions", {"meeting_key": meeting["meeting_key"]}, permanent=season < now.year
        )
        if any(s.get("session_name") == "Race" for s in sessions):
            race_meetings.append(meeting)
    race_meetings.sort(key=lambda m: m["date_start"])

    estimate = estimate_backfill(len(race_meetings))
    print(format_estimate(estimate))
    if not assume_yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    latest_key = resolve_latest_meeting_key(client, now)
    written: list[Path] = []
    for meeting in race_meetings:
        written += generate_one_meeting(
            client, repo_dir, meeting["meeting_key"], now,
            is_latest=(meeting["meeting_key"] == latest_key),
            force=force, metrics=metrics,
        )

    written += rebuild_index(repo_dir, latest_meeting_key=latest_key)
    commit_and_push(repo_dir, f"Backfill snapshots for season {season}", written)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    args = parse_args(argv)
    now = datetime.now(UTC)

    meter_provider = build_briefing_meter_provider(args.otlp_endpoint)
    metrics = create_briefing_metrics(meter_provider)

    def on_response(status_code: int) -> None:
        if status_code:
            metrics.record_source_request(status_code)

    def on_rate_limit_wait(_seconds: float) -> None:
        metrics.record_rate_limit_wait()

    client = OpenF1Client(on_response=on_response, on_rate_limit_wait=on_rate_limit_wait)

    try:
        if args.backfill:
            run_backfill(
                client, args.data_repo, args.season, now,
                force=args.force, assume_yes=args.yes, metrics=metrics,
            )
        else:
            if args.meeting == "latest":
                meeting_key = resolve_latest_meeting_key(client, now)
            else:
                meeting_key = int(args.meeting)
            latest_key = resolve_latest_meeting_key(client, now)
            written = generate_one_meeting(
                client, args.data_repo, meeting_key, now,
                is_latest=(meeting_key == latest_key),
                force=args.force, metrics=metrics,
            )
            written += rebuild_index(args.data_repo, latest_meeting_key=latest_key)
            commit_and_push(
                args.data_repo, f"Update snapshot for meeting {meeting_key}", written
            )
    finally:
        meter_provider.shutdown()


if __name__ == "__main__":
    main()
