import json
from pathlib import Path

import pytest

from pipeline.race_selector import RaceNotFoundError, resolve_session_key


def write_session(data_dir: Path, session_key: int, year: int, country: str, session_name: str) -> None:
    session_dir = data_dir / str(session_key)
    session_dir.mkdir(parents=True)
    (session_dir / "sessions.json").write_text(
        json.dumps(
            [
                {
                    "session_key": session_key,
                    "year": year,
                    "country_name": country,
                    "session_name": session_name,
                }
            ]
        )
    )


def test_resolves_exact_match(tmp_path):
    write_session(tmp_path, 9221, 2023, "Qatar", "Race")
    assert resolve_session_key(tmp_path, "2023", "Qatar", "Race") == 9221


def test_resolves_with_already_normalized_values(tmp_path):
    write_session(tmp_path, 9221, 2023, "Qatar", "Race")
    assert resolve_session_key(tmp_path, "2023", "qatar", "R") == 9221


def test_resolves_among_multiple_cached_sessions(tmp_path):
    write_session(tmp_path, 9221, 2023, "Qatar", "Race")
    write_session(tmp_path, 9222, 2023, "Abu Dhabi", "Race")
    write_session(tmp_path, 9223, 2023, "Qatar", "Qualifying")
    assert resolve_session_key(tmp_path, "2023", "Abu Dhabi", "Race") == 9222
    assert resolve_session_key(tmp_path, "2023", "Qatar", "Qualifying") == 9223


def test_missing_race_raises_with_cached_list_and_fetch_command(tmp_path):
    write_session(tmp_path, 9221, 2023, "Qatar", "Race")
    with pytest.raises(RaceNotFoundError) as exc_info:
        resolve_session_key(tmp_path, "2024", "Monaco", "Race")

    message = str(exc_info.value)
    assert "season='2024'" in message
    assert "race='monaco'" in message
    assert "qatar" in message  # lists what IS cached
    assert "pipeline.fetch_openf1" in message
    assert "--year 2024" in message
    assert "Monaco" in message


def test_empty_cache_raises_with_no_cached_races_message(tmp_path):
    with pytest.raises(RaceNotFoundError) as exc_info:
        resolve_session_key(tmp_path, "2023", "Qatar", "Race")
    assert "No races are cached" in str(exc_info.value)
