"""Publishes briefing snapshots to the pitwall-data repo: writes
data/snapshots/<meeting_key>.json, rebuilds index.json from that repo's own
working copy (not from local pipeline state, so it's correct even if some
snapshots were generated on a different machine), and commits/pushes only
when content actually changed.

Auth: a deploy key path or token is read from environment variables, never
committed. See docs/ARCHITECTURE.md / .env.example for the exact variable
names (PITWALL_DATA_REPO, PITWALL_DATA_TOKEN or
PITWALL_DATA_DEPLOY_KEY_PATH). If those aren't set, publish_snapshot()
still writes the local files and returns without attempting a git push --
that's what makes this safe to run and test before the pitwall-data repo
and its credentials exist.
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from .briefing_snapshot import content_hash

logger = logging.getLogger(__name__)

SNAPSHOT_DIR_NAME = "data/snapshots"


def snapshot_path(repo_dir: Path, meeting_key: int) -> Path:
    return repo_dir / SNAPSHOT_DIR_NAME / f"{meeting_key}.json"


def latest_path(repo_dir: Path) -> Path:
    return repo_dir / SNAPSHOT_DIR_NAME / "latest.json"


def index_path(repo_dir: Path) -> Path:
    return repo_dir / SNAPSHOT_DIR_NAME / "index.json"


def _read_existing(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_snapshot(repo_dir: Path, snapshot: dict, *, is_latest: bool) -> bool:
    """Writes the per-meeting snapshot file (and latest.json, if this is the
    current meeting). Returns True if the file content actually changed."""
    meeting_key = snapshot["meeting_key"]
    path = snapshot_path(repo_dir, meeting_key)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_existing(path)
    changed = existing is None or content_hash(existing) != content_hash(snapshot)
    if changed:
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))

    if is_latest:
        latest = latest_path(repo_dir)
        existing_latest = _read_existing(latest)
        latest_changed = (
            existing_latest is None or content_hash(existing_latest) != content_hash(snapshot)
        )
        if latest_changed:
            latest.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        changed = changed or latest_changed

    return changed


def rebuild_index(repo_dir: Path, latest_meeting_key: int | None) -> bool:
    """Rebuilds index.json by scanning the repo's own data/snapshots/
    directory, so it's correct regardless of which machine generated each
    snapshot file. Returns True if index.json content changed."""
    snapshots_dir = repo_dir / SNAPSHOT_DIR_NAME
    entries = []
    for path in sorted(snapshots_dir.glob("*.json")):
        if path.name in ("latest.json", "index.json"):
            continue
        snapshot = json.loads(path.read_text())
        entries.append(
            {
                "meeting_key": snapshot["meeting_key"],
                "meeting_name": snapshot["meeting"]["name"],
                "year": _year_from_race_start(snapshot),
                "date": snapshot["meeting"].get("race_start"),
                "final": snapshot.get("final", False),
            }
        )
    entries.sort(key=lambda e: e.get("date") or "", reverse=True)

    index = {
        "snapshots": entries,
        "latest": latest_meeting_key,
    }

    existing = _read_existing(index_path(repo_dir))
    changed = existing is None or existing != index
    if changed:
        index_path(repo_dir).write_text(json.dumps(index, indent=2, sort_keys=True))
    return changed


def _year_from_race_start(snapshot: dict) -> int | None:
    race_start = snapshot["meeting"].get("race_start")
    if not race_start:
        return None
    return datetime.fromisoformat(race_start).year


def commit_and_push(repo_dir: Path, message: str) -> bool:
    """Commits and pushes whatever's staged, if PITWALL_DATA_REPO-style env
    vars are configured. Returns True if a commit was made. No-ops (and
    logs why) if publishing isn't configured, so this is safe to call in
    environments without the pitwall-data repo wired up yet."""
    token = os.environ.get("PITWALL_DATA_TOKEN")
    deploy_key_path = os.environ.get("PITWALL_DATA_DEPLOY_KEY_PATH")
    if not token and not deploy_key_path:
        logger.info(
            "PITWALL_DATA_TOKEN/PITWALL_DATA_DEPLOY_KEY_PATH not set; "
            "writing local files only, skipping git publish."
        )
        return False

    subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True)
    status = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        logger.info("No changes to commit in %s", repo_dir)
        return False

    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", message], check=True)

    env = os.environ.copy()
    if deploy_key_path:
        env["GIT_SSH_COMMAND"] = f"ssh -i {deploy_key_path} -o IdentitiesOnly=yes"
    subprocess.run(["git", "-C", str(repo_dir), "push"], check=True, env=env)
    return True
