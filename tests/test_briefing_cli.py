from pathlib import Path

from pipeline.briefing import parse_args


def test_data_repo_explicit_flag_wins_over_everything(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_REPO", "/env/path")
    args = parse_args(["--meeting", "latest", "--data-repo", "/explicit/path"])
    assert args.data_repo == Path("/explicit/path")


def test_data_repo_falls_back_to_env_var_when_flag_not_passed(monkeypatch):
    monkeypatch.setenv("PITWALL_DATA_REPO", "/env/path")
    args = parse_args(["--meeting", "latest"])
    assert args.data_repo == Path("/env/path")


def test_data_repo_has_no_hardcoded_project_default(monkeypatch):
    # The historical bug: with neither --data-repo nor $PITWALL_DATA_REPO
    # set, this must NOT silently resolve to "data" (this project's own
    # data directory) or any other path inside the project checkout.
    monkeypatch.delenv("PITWALL_DATA_REPO", raising=False)
    args = parse_args(["--meeting", "latest"])
    assert args.data_repo != Path("data")
    assert str(args.data_repo) != "data"


def test_data_repo_default_is_a_clearly_local_output_dir(monkeypatch):
    monkeypatch.delenv("PITWALL_DATA_REPO", raising=False)
    args = parse_args(["--meeting", "latest"])
    assert "pitwall-briefing-output" in str(args.data_repo)
