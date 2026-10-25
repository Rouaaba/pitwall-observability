import json
import subprocess
from pathlib import Path

import pytest

from pipeline.snapshot_publish import (
    _THIS_PROJECT_ROOT,
    InvariantError,
    WrongRepoError,
    check_invariants,
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


def init_repo(path, remote_url="https://github.com/Rouaaba/pitwall-data.git"):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    if remote_url:
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=path, check=True)


def seed_empty_valid_index(repo_dir):
    """A minimal repo state that passes check_invariants: no meetings
    published yet, which is explicitly allowed. Used by tests that aren't
    exercising invariant-checking itself."""
    rebuild_index(repo_dir, latest_meeting_key=None)


# ---- write_snapshot ----


def test_write_snapshot_creates_file(tmp_path):
    written = write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    assert written == [snapshot_path(tmp_path, 1221)]
    assert snapshot_path(tmp_path, 1221).exists()
    assert not latest_path(tmp_path).exists()


def test_write_snapshot_writes_latest_when_flagged(tmp_path):
    written = write_snapshot(tmp_path, SNAPSHOT_A, is_latest=True)
    assert latest_path(tmp_path).exists()
    assert set(written) == {snapshot_path(tmp_path, 1221), latest_path(tmp_path)}
    assert json.loads(latest_path(tmp_path).read_text())["meeting_key"] == 1221


def test_write_snapshot_unchanged_when_content_identical_except_timestamp(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    updated = dict(SNAPSHOT_A, generated_at="2026-03-13T11:00:00+00:00")
    written = write_snapshot(tmp_path, updated, is_latest=False)
    assert written == []


def test_write_snapshot_changed_when_data_differs(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    updated = dict(SNAPSHOT_A, final=False)
    written = write_snapshot(tmp_path, updated, is_latest=False)
    assert written == [snapshot_path(tmp_path, 1221)]


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
    written = rebuild_index(tmp_path, latest_meeting_key=1221)
    assert written == [index_path(tmp_path)]
    index = json.loads(index_path(tmp_path).read_text())
    assert index["snapshots"][0]["meeting_key"] == 1221


def test_rebuild_index_unchanged_returns_empty(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)
    rebuild_index(tmp_path, latest_meeting_key=1221)
    written_again = rebuild_index(tmp_path, latest_meeting_key=1221)
    assert written_again == []


# ---- commit_and_push: scope of `git add` ----


def test_commit_and_push_noop_without_env_vars(tmp_path, monkeypatch):
    monkeypatch.delenv("PITWALL_DATA_TOKEN", raising=False)
    monkeypatch.delenv("PITWALL_DATA_DEPLOY_KEY_PATH", raising=False)
    init_repo(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("hello")
    committed = commit_and_push(tmp_path, "test commit", [f])
    assert committed is False


def test_commit_and_push_noop_with_no_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    seed_empty_valid_index(tmp_path)
    committed = commit_and_push(tmp_path, "test commit", [])
    assert committed is False


def test_commit_and_push_only_adds_the_given_paths(tmp_path, monkeypatch):
    """The core of this fix: a file that exists in the working tree but was
    NOT passed in `paths` must never be staged or committed, even though a
    blanket `git add -A` would have picked it up."""
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)

    written = write_snapshot(tmp_path, SNAPSHOT_A, is_latest=True)
    written += rebuild_index(tmp_path, latest_meeting_key=1221)

    untracked_stray = tmp_path / "some_other_file.txt"
    untracked_stray.write_text("should never be committed by this run")

    with pytest.raises(subprocess.CalledProcessError):
        # Commit succeeds; push fails only because there's no real network
        # upstream behind this fake origin URL -- that's expected and fine,
        # the thing under test is what got staged/committed before that.
        commit_and_push(tmp_path, "snapshot commit", written)

    show = subprocess.run(
        ["git", "-C", str(tmp_path), "show", "--stat", "--format=", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    assert "1221.json" in show.stdout
    assert "some_other_file.txt" not in show.stdout

    status = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    )
    assert "some_other_file.txt" in status.stdout  # still untracked, never touched


def test_commit_and_push_commits_given_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path, remote_url=None)  # no remote -> push fails, commit should still land
    f = tmp_path / "file.txt"
    f.write_text("hello")

    with pytest.raises(WrongRepoError):
        # No origin at all -- the remote guard catches this before any git
        # add/commit/push happens.
        commit_and_push(tmp_path, "test commit", [f])


def test_commit_and_push_noop_when_given_paths_have_no_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    seed_empty_valid_index(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("hello")
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "initial"], check=True)

    committed = commit_and_push(tmp_path, "no-op commit", [f])
    assert committed is False


# ---- safety guard: never publish into this project's own repo ----


def test_commit_and_push_refuses_this_projects_own_root(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    with pytest.raises(WrongRepoError):
        commit_and_push(_THIS_PROJECT_ROOT, "should never happen", [_THIS_PROJECT_ROOT / "x"])


def test_commit_and_push_refuses_a_subdirectory_of_this_project(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    target = _THIS_PROJECT_ROOT / "data"
    with pytest.raises(WrongRepoError):
        commit_and_push(target, "should never happen", [target / "x.json"])


def test_commit_and_push_refuses_relative_path_resolving_inside_project(monkeypatch, tmp_path):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    monkeypatch.chdir(_THIS_PROJECT_ROOT)
    # Mirrors the real incident: a relative --data-repo/PITWALL_DATA_REPO
    # value, resolved from inside this project's own checkout.
    target = Path("Rouaaba/pitwall-data")
    with pytest.raises(WrongRepoError):
        commit_and_push(target, "should never happen", [target / "x.json"])


# ---- safety guard: origin must look like the pitwall-data repo ----


def test_commit_and_push_refuses_a_repo_with_no_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path, remote_url=None)
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(WrongRepoError, match="could not read the 'origin' remote"):
        commit_and_push(tmp_path, "test commit", [f])


def test_commit_and_push_refuses_an_unrelated_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path, remote_url="https://github.com/someone-else/totally-unrelated.git")
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(WrongRepoError, match="doesn't look like the pitwall-data repo"):
        commit_and_push(tmp_path, "test commit", [f])


def test_commit_and_push_accepts_correct_origin_and_proceeds_to_push(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    # A valid-looking origin that doesn't actually exist on the network --
    # proves the guards passed and it got as far as attempting push.
    init_repo(tmp_path, remote_url="https://github.com/Rouaaba/pitwall-data.git")
    seed_empty_valid_index(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(subprocess.CalledProcessError):
        commit_and_push(tmp_path, "test commit", [f])

    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        check=True, capture_output=True, text=True,
    )
    assert "test commit" in log.stdout


def test_commit_and_push_remote_name_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    monkeypatch.setenv("PITWALL_DATA_REPO_NAME", "my-renamed-data-repo")
    init_repo(tmp_path, remote_url="https://github.com/Rouaaba/my-renamed-data-repo.git")
    seed_empty_valid_index(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("hello")
    with pytest.raises(subprocess.CalledProcessError):
        # Passes both guards (override matched), fails only at the network push.
        commit_and_push(tmp_path, "test commit", [f])


# ---- write_snapshot: the comparison must be scoped to repo_dir, and a
# missing file is always written regardless of what matches elsewhere ----


def test_write_snapshot_always_writes_when_file_missing_from_repo_dir(tmp_path):
    """The exact failure shape reported: a snapshot with matching content
    exists SOMEWHERE (e.g. a different directory, from an earlier
    misdirected run), but not in this repo_dir -- it must be written here
    regardless, never skipped because 'equivalent' content exists
    elsewhere. write_snapshot only ever reads via repo_dir, so this also
    guards against any future regression that accidentally widens the
    comparison beyond repo_dir."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # Write byte-identical content at a DIFFERENT location than repo_dir.
    write_snapshot(elsewhere, SNAPSHOT_A, is_latest=True)
    assert snapshot_path(elsewhere, 1221).exists()

    repo_dir = tmp_path / "real_repo"
    repo_dir.mkdir()
    assert not snapshot_path(repo_dir, 1221).exists()

    written = write_snapshot(repo_dir, SNAPSHOT_A, is_latest=True)
    assert snapshot_path(repo_dir, 1221) in written
    assert latest_path(repo_dir) in written
    assert snapshot_path(repo_dir, 1221).exists()
    assert latest_path(repo_dir).exists()


# ---- check_invariants ----


def _write_consistent_repo(repo_dir: Path) -> None:
    write_snapshot(repo_dir, SNAPSHOT_A, is_latest=True)
    rebuild_index(repo_dir, latest_meeting_key=1221)


def test_check_invariants_passes_for_consistent_repo(tmp_path):
    _write_consistent_repo(tmp_path)
    check_invariants(tmp_path)  # must not raise


def test_check_invariants_passes_with_no_meetings_published_yet(tmp_path):
    rebuild_index(tmp_path, latest_meeting_key=None)
    check_invariants(tmp_path)  # must not raise -- nothing published, nothing to check


def test_check_invariants_fails_when_index_missing(tmp_path):
    with pytest.raises(InvariantError, match="index.json is missing"):
        check_invariants(tmp_path)


def test_check_invariants_fails_when_latest_not_in_snapshots_list(tmp_path):
    _write_consistent_repo(tmp_path)
    index_path(tmp_path).write_text(
        json.dumps({"latest": 9999, "snapshots": [{"meeting_key": 1221}]})
    )
    with pytest.raises(InvariantError, match="not present in its own snapshots list"):
        check_invariants(tmp_path)


def test_check_invariants_fails_when_latest_meeting_file_missing(tmp_path):
    """The exact bug reported: index.json claims latest=1297, but
    1297.json was never actually written/committed to the data repo."""
    _write_consistent_repo(tmp_path)
    index_path(tmp_path).write_text(
        json.dumps({"latest": 1297, "snapshots": [{"meeting_key": 1297}]})
    )
    with pytest.raises(InvariantError, match=r"1297\.json.*does not exist"):
        check_invariants(tmp_path)


def test_check_invariants_fails_when_latest_json_missing(tmp_path):
    write_snapshot(tmp_path, SNAPSHOT_A, is_latest=False)  # no is_latest -> no latest.json
    rebuild_index(tmp_path, latest_meeting_key=1221)
    with pytest.raises(InvariantError, match="latest.json does not exist"):
        check_invariants(tmp_path)


# ---- commit_and_push refuses to publish when invariants fail ----


def test_commit_and_push_refuses_when_invariants_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    index_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    index_path(tmp_path).write_text(
        json.dumps({"latest": 1297, "snapshots": [{"meeting_key": 1297}]})
    )
    f = tmp_path / "unrelated.txt"
    f.write_text("hello")
    with pytest.raises(InvariantError):
        commit_and_push(tmp_path, "should be refused", [f])

    status = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--oneline"],
        capture_output=True, text=True,
    )
    assert status.stdout.strip() == ""  # nothing was ever committed


def test_commit_and_push_checks_invariants_even_with_no_new_paths(tmp_path, monkeypatch):
    """A run that wrote nothing new this time must still refuse to publish
    if the repo was already left broken by an earlier run -- the check
    must not be skipped just because `paths` is empty."""
    monkeypatch.setenv("PITWALL_DATA_TOKEN", "fake-token")
    init_repo(tmp_path)
    index_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    index_path(tmp_path).write_text(
        json.dumps({"latest": 1297, "snapshots": [{"meeting_key": 1297}]})
    )
    with pytest.raises(InvariantError):
        commit_and_push(tmp_path, "should be refused", [])
