from replay.race_labels import normalize_race, normalize_season, normalize_session, race_labels


def test_normalize_season_from_int():
    assert normalize_season(2023) == "2023"


def test_normalize_season_from_str():
    assert normalize_season("2023") == "2023"


def test_normalize_race_lowercases_and_strips():
    assert normalize_race("Qatar") == "qatar"


def test_normalize_race_collapses_spaces_to_underscores():
    assert normalize_race("Abu Dhabi") == "abu_dhabi"


def test_normalize_race_collapses_punctuation():
    assert normalize_race("São Paulo") == "s_o_paulo"


def test_normalize_session_race():
    assert normalize_session("Race") == "R"


def test_normalize_session_qualifying():
    assert normalize_session("Qualifying") == "Q"


def test_normalize_session_sprint():
    assert normalize_session("Sprint") == "S"


def test_normalize_session_sprint_qualifying():
    assert normalize_session("Sprint Qualifying") == "SQ"


def test_normalize_session_practice():
    assert normalize_session("Practice 1") == "FP1"
    assert normalize_session("Practice 2") == "FP2"
    assert normalize_session("Practice 3") == "FP3"


def test_normalize_session_is_case_insensitive():
    assert normalize_session("race") == "R"
    assert normalize_session("RACE") == "R"


def test_normalize_session_unknown_falls_back_to_slug():
    assert normalize_session("Some New Session") == "SOME_NEW_SESSION"


def test_race_labels_combines_all_three():
    assert race_labels(2023, "Qatar", "Race") == {
        "season": "2023",
        "race": "qatar",
        "session": "R",
    }
