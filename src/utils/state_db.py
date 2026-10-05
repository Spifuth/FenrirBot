"""SQLite home for FenrirBot's persistent state: data/fenrir.db.

Replaces data/scheduled_maintenances.json and data/open_incidents.json. The
first time the database is opened it is created and, in the same transaction,
whatever those two JSON files hold is imported. `PRAGMA user_version` records
that this has happened, so the import never runs twice; a crash halfway
through rolls everything back and the next boot simply tries again. The JSON
files are only ever read, never changed or deleted: they stay behind as the
pre-migration snapshot for a rollback.

data/containers.json is deliberately not here. It is a disposable mirror of
the Docker API, rebuilt at startup and every five minutes.

Rollback to the JSON-era image, without losing anything created since:

    python -m src.utils.state_db export /app/data/fenrir.db /app/data
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_FILE = DATA_DIR / "fenrir.db"
LEGACY_SCHEDULED = "scheduled_maintenances.json"
LEGACY_INCIDENTS = "open_incidents.json"

SCHEMA_VERSION = 2

_SCHEMA = (
    """
    CREATE TABLE scheduled_maintenances (
        position         INTEGER PRIMARY KEY,
        service          TEXT    NOT NULL,
        scheduled_time   TEXT    NOT NULL,  -- ISO-8601, as to_dict() writes it
        duration         TEXT    NOT NULL,
        reason           TEXT    NOT NULL,
        author_id        INTEGER NOT NULL,
        channel_id       INTEGER NOT NULL,
        maintenance_type TEXT    NOT NULL,
        announced        INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE open_incidents (
        message_id       INTEGER PRIMARY KEY,
        channel_id       INTEGER NOT NULL,
        service          TEXT    NOT NULL,
        author_id        INTEGER NOT NULL,
        duration_str     TEXT    NOT NULL,
        service_type     TEXT    NOT NULL,
        maintenance_type TEXT    NOT NULL,
        started_at       TEXT    NOT NULL   -- ISO-8601 UTC, or '' if unknown
    )
    """,
)

# Version 2: /scheduled mention:false must also silence the fire-time ping.
# DEFAULT 1 keeps every pre-existing entry pinging, as it always did.
_ADD_MENTION = "ALTER TABLE scheduled_maintenances ADD COLUMN mention INTEGER NOT NULL DEFAULT 1"

_SCHEDULED_COLUMNS = ("service", "scheduled_time", "duration", "reason",
                      "author_id", "channel_id", "maintenance_type", "announced", "mention")
_INCIDENT_COLUMNS = ("message_id", "channel_id", "service", "author_id",
                     "duration_str", "service_type", "maintenance_type", "started_at")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@contextmanager
def connect(path: Path = DB_FILE) -> Iterator[sqlite3.Connection]:
    """Open the database, creating and migrating it on first use.

    One short-lived connection per operation: the state is tiny, writes are
    rare, and it keeps every caller on whatever thread it happens to run.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: no implicit transactions; `transaction()` owns them.
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        conn.row_factory = sqlite3.Row
        _migrate(conn, path)
        yield conn


def _migrate(conn: sqlite3.Connection, path: Path) -> None:
    legacy_dir = path.parent
    if conn.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
        return
    with transaction(conn):
        # Re-check under the write lock: another opener may have won the race.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        if version < 1:
            for statement in _SCHEMA:
                conn.execute(statement)
        if version < 2:
            conn.execute(_ADD_MENTION)
        if version < 1:
            scheduled = _import_scheduled(conn, legacy_dir)
            incidents = _import_incidents(conn, legacy_dir)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    if version < 1:
        print(f"[State] Created {path}: imported {scheduled} scheduled maintenance(s) "
              f"and {incidents} open incident(s) from the JSON files")
    else:
        print(f"[State] Migrated {path} from schema {version} to {SCHEMA_VERSION}")


def _read_legacy(path: Path, expected: type):
    """The decoded JSON file, or None if it is absent, unreadable or the wrong shape."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        # ValueError covers JSONDecodeError and UnicodeDecodeError alike.
        print(f"[State] ⚠️ Not importing {path.name}: unreadable ({e!r})")
        return None
    if not isinstance(data, expected):
        print(f"[State] ⚠️ Not importing {path.name}: expected a JSON {expected.__name__}")
        return None
    return data


def _import_scheduled(conn: sqlite3.Connection, legacy_dir: Path) -> int:
    entries = _read_legacy(legacy_dir / LEGACY_SCHEDULED, list) or []
    rows = []
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise TypeError("not a scheduled maintenance")
            # from_dict() parses this on every load; refuse it now, not later.
            datetime.fromisoformat(entry["scheduled_time"])
            rows.append(_scheduled_row({
                **entry,
                "maintenance_type": entry.get("maintenance_type", "downtime"),
                "announced": entry.get("announced", False),
                "mention": entry.get("mention", True),
            }))
        except (KeyError, TypeError, ValueError) as e:
            print(f"[State] ⚠️ Skipping a malformed scheduled maintenance: {e!r}")
    _insert_scheduled(conn, rows)
    return len(rows)


def _import_incidents(conn: sqlite3.Connection, legacy_dir: Path) -> int:
    entries = _read_legacy(legacy_dir / LEGACY_INCIDENTS, dict) or {}
    count = 0
    for value in entries.values():
        try:
            # Same contract as IncidentRecord(**value): no unknown keys, and
            # only started_at may be missing (records predating the field).
            if not isinstance(value, dict) or set(value) - set(_INCIDENT_COLUMNS):
                raise TypeError("not an incident record")
            row = _incident_row({"started_at": "", **value})
        except (KeyError, TypeError, ValueError) as e:
            print(f"[State] ⚠️ Skipping a malformed open incident: {e!r}")
            continue
        conn.execute(_INSERT_INCIDENT, row)
        count += 1
    return count


def _scheduled_row(d: dict) -> tuple:
    return (str(d["service"]), str(d["scheduled_time"]), str(d["duration"]), str(d["reason"]),
            int(d["author_id"]), int(d["channel_id"]), str(d["maintenance_type"]),
            int(bool(d["announced"])), int(bool(d.get("mention", True))))


def _incident_row(d: dict) -> tuple:
    return (int(d["message_id"]), int(d["channel_id"]), str(d["service"]), int(d["author_id"]),
            str(d["duration_str"]), str(d["service_type"]), str(d["maintenance_type"]),
            str(d["started_at"]))


_INSERT_INCIDENT = (
    f"INSERT OR REPLACE INTO open_incidents ({', '.join(_INCIDENT_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_INCIDENT_COLUMNS))})"
)


def insert_incident(conn: sqlite3.Connection, record: dict) -> None:
    """Insert or overwrite one open incident, keyed by its message id."""
    conn.execute(_INSERT_INCIDENT, _incident_row(record))


def _insert_scheduled(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        f"INSERT INTO scheduled_maintenances ({', '.join(_SCHEDULED_COLUMNS)}) "
        f"VALUES ({', '.join('?' * len(_SCHEDULED_COLUMNS))})",
        rows,
    )


def _scheduled_dict(row: sqlite3.Row) -> dict:
    d = {name: row[name] for name in _SCHEDULED_COLUMNS}
    d["announced"] = bool(d["announced"])
    d["mention"] = bool(d["mention"])
    return d


class ScheduledStore:
    """The scheduled-maintenance queue, as the dicts ScheduledMaintenance
    round-trips through to_dict() / from_dict()."""

    def __init__(self, path: Path = DB_FILE):
        self.path = Path(path)

    def load(self) -> list[dict]:
        with connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM scheduled_maintenances ORDER BY position").fetchall()
        return [_scheduled_dict(r) for r in rows]

    def save(self, entries: list[dict]) -> None:
        """Replace the whole queue atomically: it is a handful of rows."""
        rows = [_scheduled_row(e) for e in entries]
        with connect(self.path) as conn, transaction(conn):
            conn.execute("DELETE FROM scheduled_maintenances")
            _insert_scheduled(conn, rows)


def export_json(db_path: Path, out_dir: Path) -> None:
    """Write the state back out as the two JSON files the JSON-era image reads."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scheduled = ScheduledStore(db_path).load()
    with connect(db_path) as conn:
        incidents = {
            str(r["message_id"]): {name: r[name] for name in _INCIDENT_COLUMNS}
            for r in conn.execute("SELECT * FROM open_incidents ORDER BY message_id")
        }
    for name, payload in ((LEGACY_SCHEDULED, scheduled), (LEGACY_INCIDENTS, incidents)):
        tmp = out_dir / f"{name}.tmp"
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(out_dir / name)
    print(f"[State] Exported {len(scheduled)} scheduled maintenance(s) and "
          f"{len(incidents)} open incident(s) to {out_dir}")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "export":
        print("usage: python -m src.utils.state_db export <fenrir.db> <out-dir>", file=sys.stderr)
        return 2
    db_path = Path(argv[1])
    if not db_path.exists():
        # connect() would create an empty database and export nothing.
        print(f"no database at {db_path}", file=sys.stderr)
        return 1
    export_json(db_path, Path(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
