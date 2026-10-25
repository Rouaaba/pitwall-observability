from pipeline.briefing_snapshot import content_hash, snapshots_differ

BASE_SNAPSHOT = {
    "meeting_key": 1221,
    "meeting": {"name": "Qatar Grand Prix"},
    "standings": [{"driver": "VER", "points": 433.0}],
    "final": False,
    "generated_at": "2026-03-13T10:00:00+00:00",
    "source_session_keys": [9221],
}


def test_content_hash_ignores_generated_at():
    a = dict(BASE_SNAPSHOT, generated_at="2026-03-13T10:00:00+00:00")
    b = dict(BASE_SNAPSHOT, generated_at="2026-03-13T10:30:00+00:00")
    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_when_data_changes():
    a = dict(BASE_SNAPSHOT)
    b = dict(BASE_SNAPSHOT, standings=[{"driver": "VER", "points": 440.0}])
    assert content_hash(a) != content_hash(b)


def test_snapshots_differ_is_false_for_identical_data_different_timestamp():
    a = dict(BASE_SNAPSHOT, generated_at="2026-03-13T10:00:00+00:00")
    b = dict(BASE_SNAPSHOT, generated_at="2026-03-13T10:30:00+00:00")
    assert snapshots_differ(a, b) is False


def test_snapshots_differ_is_true_when_data_changes():
    a = dict(BASE_SNAPSHOT)
    b = dict(BASE_SNAPSHOT, final=True)
    assert snapshots_differ(a, b) is True


def test_snapshots_differ_is_true_when_old_is_none():
    assert snapshots_differ(None, BASE_SNAPSHOT) is True
