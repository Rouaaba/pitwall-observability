import json
import subprocess
from pathlib import Path

import pytest

from pipeline.snapshot_publish import (
    _THIS_PROJECT_ROOT,
    WrongRepoError,
    commit_and_push,
    index_path,
    latest_path,
    rebuild_index,
    snapshot_path,
    write_snapshot,
)

SNAPSHOT_A = {
    "meeting_key": 1221,
    "meeting": {"name": "Qatar Grand Prix", "race_start": "2023-10-08T17:00:00+00:00"},
    "standings": [{"driver": "VER"}],
    "final": True,
    "generated_at": "2026-03-13T10:00:00+00:00",
}

SNAPSHOT_B = {
    "meeting_key": 1222,
    "meeting": {"name": "Abu Dhabi Grand Prix", "race_start": "2023-11-26T13:00:00+00:00"},
    "standings": [{"driver": "VER"}],
    "final": False,
    "generated_at": "2026-03-13T10:00:00+00:00",
}


def init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


# ---- write_snapshot ----


def test_write_snapshot_creates_file(tmp_path):
    changed = write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    assert changed is True
    assert snapshot_path(tmp_path, 1221).exists()
    assert not latest_path(tmp_path).exists()


def test_write_snapshot_writes_latest_when_flagged(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=True)
    assert latest_path(tmp_path).exists()
    assert json.loads(latest_path(tmp_path).read_text())["meeting_key"] == 1221


def test_write_snapshot_unchanged_when_content_identical_except_timestamp(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    updated = dict(SNAPSHOT_A, generated_at="2026-03-13T11:00:00+00:00")
    changed = write_snapshot(tmp_path, updated, is_latest=False)
    assert changed is False


def test_write_snapshot_changed_when_data_differs(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    updated = dict(SNAPSHOT_A, final=False)
    changed = write_snapshot(tmp_path, updated, is_latest=False)
    assert changed is True


# ---- rebuild_index ----


def test_rebuild_index_lists_all_snapshots_sorted_newest_first(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    write_snapshot(tmp_path, SNAPSHOT_B, is_latest=True)
    rebuild_index(tmp_path, latest_meeting_key=1222)

    index = json.loads(index_path(tmp_path).read_text())
    assert index["latest"] == 1222
    assert [s["meeting_key"] for s in index["snapshots"]] == [1222, 1221]
    assert index["snapshots"][0]["meeting_name"] == "Abu Dhabi Grand Prix"
    assert index["snapshots"][0]["final"] is False
    assert index["snapshots"][1]["final"] is True


def test_rebuild_index_ignores_latest_and_index_files_themselves(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=True)
    rebuild_index(tmp_path, latest_meeting_key=1221)
    index = json.loads(index_path(tmp_path).read_text())
    assert len(index["snapshots"]) == 1


def test_rebuild_index_reads_from_repo_working_copy_not_local_state(tmp_path):
    # Simulates snapshots having been written by a different process/machine:
    # just drop files directly on disk, no in-memory state involved.
    snapshot_path(tmp_path, 1221).parent.mkdir(parents=True, exist_ok=True)
    snapshot_path(tmp_path, 1221).write_text(json.dumps(SNAPSHOT_A))
    changed = rebuild_index(tmp_path, latest_meeting_key=1221)
    assert changed is True
    index = json.loads(index_path(tmp_path).read_text())
    assert index["snapshots"][0]["meeting_key"] == 1221


def test_rebuild_index_unchanged_returns_false(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    rebuild_index(tmp_path, latest_meeting_key=1221)
    changed_again = rebuild_index(tmp_path, latest_meeting_key=1221)
    assert changed_again is False


# ---- commit_and_push ----


def test_commit_and_push_noop_without_env_vars(tmp_path, monkeypatch):
    monkeypatch.delenv("PITWALL_DATA_TOKEN", raising=False)
    monkeypatch.delenv("PITWALL_DATA_DEPLOY_KEY_PATH", raising=False)
    init_repo(tmp_path)
    (tmp_path / "file.txt").write_text("hello")
    committed = commit_and_push(tmp_path, "test commit")
    assert committed is False


def test_commit_and_push_commits_when_token_set_and_no_remote(tmp_path, monkeypatch):
    # No real remote configured, so push would fail -- only test the
    # add+commit path by stubbing push out via a repo with no remote and
    # catching the expected failure, OR test commit in isolation by
    # confirming the commit lands before push is attempted.
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    (tmp_path / "file.txt").write_text("hello")

    with pytest.raises(subprocess.CalledProcessError):
        # push fails because there's no remote -- but the commit itself
        # should have succeeded first.
        commit_and_push(tmp_path, "test commit")

    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        check=True, capture_output=True, text=True,
    )
    assert "test commit" in log.stdout


def test_commit_and_push_noop_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    (tmp_path / "file.txt").write_text("hello")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "initial"], check=True)

    committed = commit_and_push(tmp_path, "no-op commit")
    assert committed is False


# ---- safety guard: never publish into this project's own repo ----


def test_commit_and_push_refuses_this_projects_own_root(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    with pytest.raises(WrongRepoError):
        commit_and_push(_THIS_PROJECT_ROOT, "should never happen")


def test_commit_and_push_refuses_a_subdirectory_of_this_project(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    with pytest.raises(WrongRepoError):
        commit_and_push(_THIS_PROJECT_ROOT / "data", "should never happen")


def test_commit_and_push_refuses_relative_path_resolving_inside_project(monkeypatch, tmp_path):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    monkeypatch.chdir(_THIS_PROJECT_ROOT)
    # Mirrors the real incident: a relative --data-repo/PITWALL_DATA_REPO
    # value, resolved from inside this project's own checkout.
    with pytest.raises(WrongRepoError):
        commit_and_push(Path("Rouaaba/pitwall-data"), "should never happen")


def test_commit_and_push_allows_a_sibling_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    sibling = tmp_path / "pitwall-data"
    sibling.mkdir()
    init_repo(sibling)
    (sibling / "file.txt").write_text("hello")
    with pytest.raises(subprocess.CalledProcessError):
        # Fails at push (no remote configured) -- proves the guard did NOT
        # block a genuinely separate repo, only ones inside this project.
        commit_and_push(sibling, "ok commit")
