"""Persistence for open incident announcements.

discord.py views live in memory. Without a record on disk, every restart
leaves the buttons on an open announcement dead ("This interaction failed"),
with no way to close the incident from the message.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import state_db


@dataclass
class IncidentRecord:
    message_id: int
    channel_id: int
    service: str
    author_id: int
    duration_str: str
    service_type: str      # ServiceType value
    maintenance_type: str  # MaintenanceType value
    started_at: str = ""   # ISO-8601 UTC; "" for records written before this field existed


class IncidentStore:
    """message_id -> IncidentRecord, in the open_incidents table of data/fenrir.db."""

    def __init__(self, path: Path = state_db.DB_FILE):
        self.path = Path(path)

    # An incident closed by any route other than the buttons or /up leaves its
    # record behind. Without a ceiling the table grows forever and every restart
    # re-registers enabled buttons on long-dead announcements, where a late
    # click would report a fabricated multi-week duration.
    MAX_AGE = timedelta(days=7)

    def _is_stale(self, record: IncidentRecord, now: datetime) -> bool:
        if not record.started_at:
            return False  # unknown age: keep it rather than guess
        try:
            started = datetime.fromisoformat(record.started_at)
        except ValueError:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return (now - started) > self.MAX_AGE

    @staticmethod
    def _all(conn: sqlite3.Connection) -> list[IncidentRecord]:
        rows = conn.execute("SELECT * FROM open_incidents ORDER BY message_id").fetchall()
        return [IncidentRecord(**dict(row)) for row in rows]

    def _prune_stale(self, conn: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc)
        stale = [(r.message_id,) for r in self._all(conn) if self._is_stale(r, now)]
        conn.executemany("DELETE FROM open_incidents WHERE message_id = ?", stale)

    def load(self) -> dict[int, IncidentRecord]:
        try:
            with state_db.connect(self.path) as conn:
                records = self._all(conn)
        except sqlite3.Error as e:
            # Startup revives whatever this returns; an unreadable database
            # must degrade to "no incidents", as a corrupt JSON file did.
            print(f"[Incidents] ⚠️ Could not read {self.path}: {e!r}")
            return {}
        now = datetime.now(timezone.utc)
        return {r.message_id: r for r in records if not self._is_stale(r, now)}

    def add(self, record: IncidentRecord) -> None:
        with state_db.connect(self.path) as conn, state_db.transaction(conn):
            self._prune_stale(conn)
            state_db.insert_incident(conn, asdict(record))

    def remove(self, message_id: int) -> None:
        with state_db.connect(self.path) as conn, state_db.transaction(conn):
            self._prune_stale(conn)
            conn.execute("DELETE FROM open_incidents WHERE message_id = ?", (message_id,))

    def remove_by_service(self, service: str) -> int:
        """Delete every record whose service matches (case-insensitively).

        Used when a service is announced restored via /up, so a closed
        incident's buttons don't get revived with a fabricated duration on
        the next restart. Returns the number of records removed.
        """
        target = service.lower()
        with state_db.connect(self.path) as conn, state_db.transaction(conn):
            self._prune_stale(conn)
            # Compared in Python, not SQL: SQLite's lower() only folds ASCII.
            matching = [(r.message_id,) for r in self._all(conn) if r.service.lower() == target]
            conn.executemany("DELETE FROM open_incidents WHERE message_id = ?", matching)
        return len(matching)


incident_store = IncidentStore()
