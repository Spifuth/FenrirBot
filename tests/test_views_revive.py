"""Confirms a view revived from disk carries the true incident start time,
not the moment of revival.

No Discord connection is made anywhere here: DowntimeView.__init__ never
touches the network, and from_record's `store` argument is a real
IncidentStore pointed at tmp_path so no test touches the module-level
singleton's real data/ path.
"""

from datetime import datetime, timedelta, timezone

from src.utils.incidents import IncidentRecord, IncidentStore
from src.utils.views import DowntimeView


def _record(started_at: str) -> IncidentRecord:
    return IncidentRecord(
        message_id=111,
        channel_id=222,
        service="traefik",
        author_id=333,
        duration_str="30 minutes",
        service_type="container",
        maintenance_type="security",
        started_at=started_at,
    )


def test_from_record_with_known_started_at_sets_start_time_to_it(tmp_path):
    store = IncidentStore(path=tmp_path / "open_incidents.json")
    known = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    record = _record(started_at=known.isoformat())

    view = DowntimeView.from_record(record, store)

    assert view.start_time == known


def test_from_record_with_empty_started_at_falls_back_to_now(tmp_path):
    store = IncidentStore(path=tmp_path / "open_incidents.json")
    record = _record(started_at="")

    before = datetime.now(timezone.utc)
    view = DowntimeView.from_record(record, store)
    after = datetime.now(timezone.utc)

    assert view.start_time.tzinfo is not None
    # Generous window rather than exact equality -- we only care that it
    # fell back to "now", not the precise instant this test executed.
    assert before - timedelta(seconds=60) <= view.start_time <= after + timedelta(seconds=60)


def test_from_record_with_malformed_started_at_does_not_raise(tmp_path):
    store = IncidentStore(path=tmp_path / "open_incidents.json")
    record = _record(started_at="not-a-date")

    before = datetime.now(timezone.utc)
    view = DowntimeView.from_record(record, store)
    after = datetime.now(timezone.utc)

    assert view.start_time.tzinfo is not None
    assert before - timedelta(seconds=60) <= view.start_time <= after + timedelta(seconds=60)


def test_from_record_with_naive_started_at_is_coerced_to_utc(tmp_path):
    # No UTC offset in the string -- datetime.fromisoformat parses this fine
    # but yields a naive datetime. restore_button later computes
    # datetime.now(timezone.utc) - self.start_time, which raises TypeError
    # unless from_record coerces it to aware UTC first.
    store = IncidentStore(path=tmp_path / "open_incidents.json")
    record = _record(started_at="2026-01-01T12:00:00")

    view = DowntimeView.from_record(record, store)

    assert view.start_time.tzinfo is not None
    # Must not silently shift the wall-clock value: it becomes UTC, not
    # reinterpreted in some other zone.
    assert view.start_time == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_view_is_persistent():
    # Pins the headline behaviour this task exists for: timeout=None + a
    # stable custom_id on every child is what makes bot.add_view() able to
    # revive the view after a restart. If either regressed, add_view() would
    # raise, the per-record except in setup_hook would swallow it, and the
    # bot would silently degrade back to the original dead-button bug.
    view = DowntimeView(service="traefik", author_id=1)
    assert view.is_persistent()
    assert view.timeout is None
    assert sorted(c.custom_id for c in view.children) == [
        "fenrir:incident:cancel", "fenrir:incident:restore",
    ]
