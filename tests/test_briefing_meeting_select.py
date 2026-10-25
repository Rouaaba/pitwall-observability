from datetime import UTC, datetime

from pipeline.briefing_meeting_select import resolve_latest_meeting_key

# A 3-weekend season for testing: previous GP (already finished), this GP
# (the one in question), next GP (hasn't started yet).
PREVIOUS_GP = {
    "meeting_key": 1001,
    "year": 2026,
    "date_start": "2026-03-06T08:00:00+00:00",
    "date_end": "2026-03-08T15:00:00+00:00",
}
THIS_GP = {
    "meeting_key": 1002,
    "year": 2026,
    "date_start": "2026-03-13T08:00:00+00:00",
    "date_end": "2026-03-15T15:00:00+00:00",
}
NEXT_GP = {
    "meeting_key": 1003,
    "year": 2026,
    "date_start": "2026-03-20T08:00:00+00:00",
    "date_end": "2026-03-22T15:00:00+00:00",
}

RACE_SESSIONS = {
    1001: [{"session_name": "Race"}],
    1002: [{"session_name": "Race"}],
    1003: [{"session_name": "Race"}],
}


class FakeClient:
    def __init__(self, meetings, sessions_by_meeting):
        self.meetings = meetings
        self.sessions_by_meeting = sessions_by_meeting
        self.calls = []

    def get(self, endpoint, params, *, permanent=False):
        self.calls.append((endpoint, params))
        if endpoint == "meetings":
            return self.meetings
        if endpoint == "sessions":
            return self.sessions_by_meeting.get(params["meeting_key"], [])
        raise AssertionError(f"unexpected endpoint {endpoint}")


def make_client():
    return FakeClient([PREVIOUS_GP, THIS_GP, NEXT_GP], RACE_SESSIONS)


def test_friday_of_race_weekend_points_at_this_weekend_not_previous():
    # Friday during THIS_GP's weekend (date_start <= now <= date_end), before
    # the Race session itself has happened.
    now = datetime(2026, 3, 13, 10, 0, tzinfo=UTC)
    client = make_client()
    assert resolve_latest_meeting_key(client, now) == 1002


def test_sunday_night_after_race_still_points_at_this_weekend():
    # Race has finished but we're still within the meeting's date_end window.
    now = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
    client = make_client()
    assert resolve_latest_meeting_key(client, now) == 1002


def test_midweek_points_at_next_upcoming_weekend_not_previous():
    # Between THIS_GP ending and NEXT_GP starting: a pre-race view should
    # already show the upcoming weekend, not the one that just finished.
    now = datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    client = make_client()
    assert resolve_latest_meeting_key(client, now) == 1003


def test_midweek_before_any_weekend_started_points_at_first_upcoming():
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    client = make_client()
    assert resolve_latest_meeting_key(client, now) == 1001


def test_after_final_weekend_of_season_falls_back_to_most_recent():
    now = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    client = make_client()
    assert resolve_latest_meeting_key(client, now) == 1003


def test_testing_meetings_are_skipped():
    testing = {
        "meeting_key": 999,
        "year": 2026,
        "date_start": "2026-03-10T08:00:00+00:00",
        "date_end": "2026-03-10T15:00:00+00:00",
    }
    sessions = dict(RACE_SESSIONS)
    sessions[999] = [{"session_name": "Day 1"}]
    client = FakeClient([testing, THIS_GP], sessions)
    # Midweek, after testing but before THIS_GP: must skip the testing
    # meeting and resolve to the next real race weekend.
    now = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)
    assert resolve_latest_meeting_key(client, now) == 1002
