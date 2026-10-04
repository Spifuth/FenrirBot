"""The SQLite state store and its one-time import of the legacy JSON files.

tests/fixtures/legacy_data/ holds a scheduled_maintenances.json and an
open_incidents.json in exactly the shape the JSON-era code wrote them
(ScheduledMaintenance.to_dict() lists, IncidentStore's str(message_id) map,
json.dump's ASCII escaping), including one entry of each from before a field
was added. Every id, name and reason in them is invented; the live files were
empty when this was written. Each test copies them into tmp_path, so the
fixtures themselves are never modified.
"""

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.cogs.downtime import ScheduledMaintenance
from src.utils import state_db
from src.utils.incidents import IncidentStore
from src.utils.state_db import ScheduledStore

FIXTURES = Path(__file__).parent / "fixtures" / "legacy_data"
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def data_dir(tmp_path):
    """A data/ directory as the JSON-era bot left it."""
    d = tmp_path / "data"
    shutil.copytree(FIXTURES, d)
    return d


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── first boot: the one-time import ────────────────────────────────────────

def test_first_open_imports_every_scheduled_maintenance_in_order(data_dir):
    rows = ScheduledStore(data_dir / "fenrir.db").load()

    assert [r["service"] for r in rows] == ["svc-alpha", "stack-beta", "svc-gamma"]
    assert rows[0] == _fixture("scheduled_maintenances.json")[0]


def test_imported_rows_rebuild_into_the_same_maintenances_the_json_held(data_dir):
    rows = ScheduledStore(data_dir / "fenrir.db").load()

    rebuilt = [ScheduledMaintenance.from_dict(r) for r in rows]
    from_json = [ScheduledMaintenance.from_dict(d) for d in _fixture("scheduled_maintenances.json")]
    assert rebuilt == from_json
    assert rebuilt[0].scheduled_time.tzinfo is not None
    # The pre-maintenance_type entry gets the same defaults from_dict gave it.
    assert (rebuilt[2].maintenance_type, rebuilt[2].announced) == ("downtime", False)


def test_first_open_imports_every_open_incident(data_dir):
    records = IncidentStore(data_dir / "fenrir.db").load()

    assert sorted(records) == [300000000000000005, 300000000000000006]
    alpha = records[300000000000000005]
    assert (alpha.service, alpha.maintenance_type, alpha.started_at) == (
        "svc-alpha", "security", "2099-01-01T10:00:00+00:00",
    )
    assert records[300000000000000006].started_at == "", "pre-started_at record keeps the default"


def test_the_import_happens_whichever_store_opens_the_db_first(data_dir):
    IncidentStore(data_dir / "fenrir.db").load()

    assert len(ScheduledStore(data_dir / "fenrir.db").load()) == 3


def test_the_legacy_json_files_are_left_untouched(data_dir):
    before = {p.name: p.read_bytes() for p in data_dir.glob("*.json")}

    ScheduledStore(data_dir / "fenrir.db").load()

    assert {p.name: p.read_bytes() for p in data_dir.glob("*.json")} == before


def test_the_import_runs_once_and_never_again(data_dir):
    db = data_dir / "fenrir.db"
    store = ScheduledStore(db)
    store.load()
    store.save([])  # the operator cancels everything after the migration

    # A JSON file still on disk on the next boot must not resurrect anything.
    assert ScheduledStore(db).load() == []
    assert IncidentStore(db).load().keys() == {300000000000000005, 300000000000000006}


def test_a_crash_mid_import_leaves_nothing_half_done(data_dir, monkeypatch):
    db = data_dir / "fenrir.db"

    def boom(conn, legacy_dir):
        raise RuntimeError("power cut")
    monkeypatch.setattr(state_db, "_import_incidents", boom)
    with pytest.raises(RuntimeError):
        ScheduledStore(db).load()
    monkeypatch.undo()

    # Scheduled rows were inserted before the crash; they must have been
    # rolled back with it, or this retry would import them a second time.
    assert len(ScheduledStore(db).load()) == 3
    assert len(IncidentStore(db).load()) == 2


def test_a_fresh_install_with_no_json_starts_empty(tmp_path):
    db = tmp_path / "data" / "fenrir.db"

    assert ScheduledStore(db).load() == []
    assert IncidentStore(db).load() == {}
    assert db.exists()


@pytest.mark.parametrize("payload", [
    b"{ this is not json",
    b"null",
    b'{"not": "a list"}',
    b"\xff\xfe\x00\x01not valid utf-8",
])
def test_an_unreadable_scheduled_file_imports_nothing_and_does_not_block_boot(tmp_path, payload):
    (tmp_path / "scheduled_maintenances.json").write_bytes(payload)

    assert ScheduledStore(tmp_path / "fenrir.db").load() == []


@pytest.mark.parametrize("payload", [b"{ nope", b"[]", b"null", b"\xff\xfe\x00\x01"])
def test_an_unreadable_incident_file_imports_nothing_and_does_not_block_boot(tmp_path, payload):
    (tmp_path / "open_incidents.json").write_bytes(payload)

    assert IncidentStore(tmp_path / "fenrir.db").load() == {}


def test_one_malformed_entry_is_skipped_and_the_rest_imported(tmp_path):
    good = _fixture("scheduled_maintenances.json")[0]
    (tmp_path / "scheduled_maintenances.json").write_text(json.dumps([
        {"service": "no-time"},
        {**good, "scheduled_time": "not-a-date"},
        ["not", "a", "dict"],
        good,
    ]))
    incidents = _fixture("open_incidents.json")
    incidents["1"] = {"message_id": 1, "unexpected": "field"}
    (tmp_path / "open_incidents.json").write_text(json.dumps(incidents))

    assert [r["service"] for r in ScheduledStore(tmp_path / "fenrir.db").load()] == ["svc-alpha"]
    assert len(IncidentStore(tmp_path / "fenrir.db").load()) == 2


def test_the_schema_version_is_recorded(data_dir):
    db = data_dir / "fenrir.db"
    ScheduledStore(db).load()

    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == state_db.SCHEMA_VERSION


# ── steady state: the scheduled store ──────────────────────────────────────

def test_save_replaces_the_whole_queue_and_keeps_its_order(tmp_path):
    store = ScheduledStore(tmp_path / "fenrir.db")
    rows = _fixture("scheduled_maintenances.json")
    full = [ScheduledMaintenance.from_dict(d).to_dict() for d in rows]

    store.save(full)
    store.save(list(reversed(full[:2])))

    assert [r["service"] for r in ScheduledStore(store.path).load()] == ["stack-beta", "svc-alpha"]


def test_the_downtime_cog_round_trips_its_queue_through_the_db(tmp_path, monkeypatch):
    import src.cogs.downtime as downtime_module
    from src.cogs.downtime import DowntimeCog

    monkeypatch.setattr(downtime_module, "scheduled_store", ScheduledStore(tmp_path / "fenrir.db"))
    queue = [ScheduledMaintenance.from_dict(d) for d in _fixture("scheduled_maintenances.json")]

    writer = DowntimeCog.__new__(DowntimeCog)
    writer._scheduled_maintenances = queue
    writer._save_scheduled_maintenances()

    reader = DowntimeCog.__new__(DowntimeCog)
    reader._scheduled_maintenances = []
    reader._load_scheduled_maintenances()
    assert reader._scheduled_maintenances == queue


def test_the_downtime_cog_survives_an_unopenable_db(tmp_path, monkeypatch, capsys):
    import src.cogs.downtime as downtime_module
    from src.cogs.downtime import DowntimeCog

    not_a_db = tmp_path / "fenrir.db"
    not_a_db.write_bytes(b"this is not an sqlite file" * 100)
    monkeypatch.setattr(downtime_module, "scheduled_store", ScheduledStore(not_a_db))

    cog = DowntimeCog.__new__(DowntimeCog)
    cog._scheduled_maintenances = ["sentinel"]
    cog._load_scheduled_maintenances()
    assert cog._scheduled_maintenances == []
    cog._save_scheduled_maintenances()  # must log, not raise
    assert "Error" in capsys.readouterr().out


# ── rollback: export back to the legacy JSON files ─────────────────────────

def test_export_writes_json_the_previous_image_reads_back_unchanged(data_dir, tmp_path):
    db = data_dir / "fenrir.db"
    ScheduledStore(db).load()  # triggers the import
    out = tmp_path / "rollback"

    state_db.export_json(db, out)

    scheduled = json.loads((out / "scheduled_maintenances.json").read_text())
    assert [ScheduledMaintenance.from_dict(d) for d in scheduled] == [
        ScheduledMaintenance.from_dict(d) for d in _fixture("scheduled_maintenances.json")
    ]
    incidents = json.loads((out / "open_incidents.json").read_text())
    assert set(incidents) == {"300000000000000005", "300000000000000006"}
    assert incidents["300000000000000006"]["started_at"] == ""
    assert incidents["300000000000000005"] == _fixture("open_incidents.json")["300000000000000005"]


def test_export_is_runnable_as_a_module(data_dir, tmp_path):
    db = data_dir / "fenrir.db"
    ScheduledStore(db).load()
    out = tmp_path / "rollback"

    result = subprocess.run(
        [sys.executable, "-m", "src.utils.state_db", "export", str(db), str(out)],
        cwd=REPO, capture_output=True, text=True, check=False,
        env={"PYTHON_DOTENV_DISABLED": "1", "PATH": ""},
    )

    assert result.returncode == 0, result.stderr
    assert len(json.loads((out / "scheduled_maintenances.json").read_text())) == 3
