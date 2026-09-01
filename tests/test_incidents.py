import json

import pytest

from src.utils.incidents import IncidentRecord, IncidentStore


@pytest.fixture
def store(tmp_path):
    return IncidentStore(path=tmp_path / "open_incidents.json")


def _record(message_id=111, started_at=""):
    return IncidentRecord(
        message_id=message_id,
        channel_id=222,
        service="traefik",
        author_id=333,
        duration_str="30 minutes",
        service_type="container",
        maintenance_type="security",
        started_at=started_at,
    )


def test_add_then_load_round_trips(store):
    store.add(_record())
    reloaded = IncidentStore(path=store.path).load()
    assert reloaded[111].service == "traefik"
    assert reloaded[111].maintenance_type == "security"


def test_remove_deletes_the_record(store):
    store.add(_record())
    store.remove(111)
    assert IncidentStore(path=store.path).load() == {}


def test_remove_is_idempotent(store):
    store.remove(999)  # must not raise
    assert store.load() == {}


def test_load_returns_empty_when_file_missing(store):
    assert store.load() == {}


def test_load_returns_empty_on_corrupt_json(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{ this is not json")
    assert store.load() == {}


def test_write_is_atomic_no_tmp_left_behind(store):
    store.add(_record())
    leftovers = list(store.path.parent.glob("*.tmp"))
    assert leftovers == []
    assert json.loads(store.path.read_text())["111"]["service"] == "traefik"


def test_started_at_round_trips(store):
    store.add(_record(started_at="2026-01-01T12:00:00+00:00"))
    reloaded = IncidentStore(path=store.path).load()
    assert reloaded[111].started_at == "2026-01-01T12:00:00+00:00"


def test_load_tolerates_a_record_json_without_started_at(store):
    # Mimics a file written by a version of this store that predates the
    # started_at field: the dataclass default ("") must apply on load
    # instead of raising.
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({
        "111": {
            "message_id": 111,
            "channel_id": 222,
            "service": "traefik",
            "author_id": 333,
            "duration_str": "30 minutes",
            "service_type": "container",
            "maintenance_type": "security",
        }
    }))
    reloaded = IncidentStore(path=store.path).load()
    assert reloaded[111].started_at == ""
