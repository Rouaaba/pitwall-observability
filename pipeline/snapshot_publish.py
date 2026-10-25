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

# This project's own repo root -- used as a hard safety guard in
# commit_and_push so a misconfigured --data-repo/PITWALL_DATA_REPO can never
# again commit snapshot files into pitwall-observability itself, which
# happened once when PITWALL_DATA_REPO_PATH (a typo'd env var name the code
# used to read) silently fell back to a path inside this checkout.
_THIS_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Substrings that must appear in the data repo's origin remote URL before
# commit_and_push will push to it -- a second, independent check alongside
# the path-containment guard above, since a correct *path* doesn't by
# itself prove it's the correct *repo* (e.g. a stale/wrong clone at that
# path). Override with PITWALL_DATA_REPO_NAME if the repo is ever renamed.
DEFAULT_EXPECTED_REMOTE_SUBSTRING = "pitwall-data"


class WrongRepoError(Exception):
    pass


class InvariantError(Exception):
    """Raised by check_invariants when the data repo's working copy is
    internally inconsistent -- e.g. index.json claims a "latest" meeting
    whose snapshot file doesn't actually exist. A run that hits this must
    not commit/push, since doing so would publish (or perpetuate) broken
    state for consumers reading index.json."""


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


def write_snapshot(repo_dir: Path, snapshot: dict, *, is_latest: bool) -> list[Path]:
    """Writes the per-meeting snapshot file (and latest.json, if this is the
    current meeting). Returns the paths that were actually written (empty
    list if nothing changed) -- the caller passes this straight into
    commit_and_push so only files this run touched get committed, never a
    blanket `git add -A`."""
    meeting_key = snapshot["meeting_key"]
    path = snapshot_path(repo_dir, meeting_key)
    path.parent.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    existing = _read_existing(path)
    changed = existing is None or content_hash(existing) != content_hash(snapshot)
    if changed:
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        written.append(path)

    if is_latest:
        latest = latest_path(repo_dir)
        existing_latest = _read_existing(latest)
        latest_changed = (
            existing_latest is None or content_hash(existing_latest) != content_hash(snapshot)
        )
        if latest_changed:
            latest.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
            written.append(latest)

    return written


def rebuild_index(repo_dir: Path, latest_meeting_key: int | None) -> list[Path]:
    """Rebuilds index.json by scanning the repo's own data/snapshots/
    directory, so it's correct regardless of which machine generated each
    snapshot file. Returns [index_path] if it changed, else []."""
    snapshots_dir = repo_dir / SNAPSHOT_DIR_NAME
    snapshots_dir.mkdir(parents=True, exist_ok=True)
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
        return [index_path(repo_dir)]
    return []


def check_invariants(repo_dir: Path) -> None:
    """Checked before every commit. Raises InvariantError (without writing
    or committing anything) if the data repo's working copy is internally
    inconsistent:

      - index.json's "latest" entry must be present in its own
        "snapshots" list.
      - both <latest>.json and latest.json must actually exist on disk.

    This exists because a run can write snapshot/index files to the repo's
    working copy and then fail or be interrupted before (or during) the
    git commit/push -- e.g. a crash, a network failure on push, or an
    earlier run writing into the wrong repo entirely (see
    _guard_against_this_project_repo / _guard_against_wrong_remote). A
    later run's "only rewrite if content changed" check compares against
    whatever is sitting in the working copy, which can silently paper over
    that kind of partial/interrupted state -- this is the explicit backstop
    that catches it before anything gets published.
    """
    index = _read_existing(index_path(repo_dir))
    if index is None:
        raise InvariantError(f"index.json is missing in {repo_dir}")

    latest_key = index.get("latest")
    if latest_key is None:
        return  # no meetings published yet; nothing to check

    listed_keys = {s["meeting_key"] for s in index.get("snapshots", [])}
    if latest_key not in listed_keys:
        raise InvariantError(
            f"index.json's latest={latest_key!r} is not present in its own "
            f"snapshots list ({sorted(listed_keys)})"
        )

    latest_meeting_file = snapshot_path(repo_dir, latest_key)
    if not latest_meeting_file.exists():
        raise InvariantError(
            f"index.json's latest={latest_key!r} but {latest_meeting_file} does not exist"
        )

    if not latest_path(repo_dir).exists():
        raise InvariantError(f"{latest_path(repo_dir)} does not exist")


def _year_from_race_start(snapshot: dict) -> int | None:
    race_start = snapshot["meeting"].get("race_start")
    if not race_start:
        return None
    return datetime.fromisoformat(race_start).year


def _guard_against_this_project_repo(repo_dir: Path) -> None:
    """Refuses to commit/push if repo_dir resolves inside (or to) this
    project's own checkout -- the exact mistake that happened once, where a
    misconfigured data-repo path silently fell back to a path inside
    pitwall-observability and its commit landed in that repo instead of
    pitwall-data."""
    resolved = repo_dir.resolve()
    if resolved == _THIS_PROJECT_ROOT or _THIS_PROJECT_ROOT in resolved.parents:
        raise WrongRepoError(
            f"Refusing to commit/push: --data-repo resolved to {resolved}, "
            f"which is inside this project's own checkout ({_THIS_PROJECT_ROOT}). "
            "Set --data-repo or $PITWALL_DATA_REPO to a separate pitwall-data checkout."
        )


def _guard_against_wrong_remote(repo_dir: Path) -> None:
    """Refuses to commit/push if repo_dir's own git origin doesn't look like
    the pitwall-data repo. A correct PATH doesn't by itself prove it's the
    correct REPO -- this is an independent check from the path-containment
    guard above."""
    expected = os.environ.get("PITWALL_DATA_REPO_NAME", DEFAULT_EXPECTED_REMOTE_SUBSTRING)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise WrongRepoError(
            f"Refusing to commit/push: could not read the 'origin' remote for "
            f"{repo_dir} ({result.stderr.strip()}). Is this a git repo with an "
            "origin configured?"
        )
    origin_url = result.stdout.strip()
    if expected not in origin_url:
        raise WrongRepoError(
            f"Refusing to commit/push: {repo_dir}'s origin remote is "
            f"{origin_url!r}, which doesn't look like the pitwall-data repo "
            f"(expected {expected!r} in the URL). Set $PITWALL_DATA_REPO_NAME "
            "if the repo has been renamed."
        )


def commit_and_push(repo_dir: Path, message: str, paths: list[Path]) -> bool:
    """Commits and pushes exactly `paths` (the files this run actually
    wrote), if PITWALL_DATA_REPO-style env vars are configured. Returns
    True if a commit was made. No-ops (and logs why) if publishing isn't
    configured, so this is safe to call in environments without the
    pitwall-data repo wired up yet.

    Deliberately never uses `git add -A`/`git add .`: this repo is shared
    with other runs and potentially other machines, and a blanket add would
    stage anything else sitting in the working copy (stray local files,
    another process's in-progress writes) as part of this run's commit.

    check_invariants() is run unconditionally, even if `paths` is empty --
    a run that wrote nothing new must still refuse to publish if the repo
    is already in a broken state left by an earlier run (e.g. index.json
    references a snapshot file that was never actually committed), rather
    than silently returning before that gets checked.
    """
    token = os.environ.get("PITWALL_DATA_TOKEN")
    deploy_key_path = os.environ.get("PITWALL_DATA_DEPLOY_KEY_PATH")
    if not token and not deploy_key_path:
        logger.info(
            "PITWALL_DATA_TOKEN/PITWALL_DATA_DEPLOY_KEY_PATH not set; "
            "writing local files only, skipping git publish."
        )
        return False

    _guard_against_this_project_repo(repo_dir)
    _guard_against_wrong_remote(repo_dir)
    check_invariants(repo_dir)

    if not paths:
        logger.info("No snapshot files were written this run; nothing to commit.")
        return False

    subprocess.run(
        ["git", "-C", str(repo_dir), "add", "--", *[str(p) for p in paths]], check=True
    )
    status = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--porcelain", "--", *[str(p) for p in paths]],
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
