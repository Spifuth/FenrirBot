"""Persistence for open incident announcements.

discord.py views live in memory. Without a record on disk, every restart
leaves the buttons on an open announcement dead ("This interaction failed"),
with no way to close the incident from the message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

STORE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "open_incidents.json"


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
    """A tiny JSON-backed map of message_id -> IncidentRecord."""

    def __init__(self, path: Path = STORE_FILE):
        self.path = Path(path)

    def load(self) -> dict[int, IncidentRecord]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # ValueError covers both json.JSONDecodeError and the
            # UnicodeDecodeError raised by read_text() on invalid UTF-8.
            return {}
        if not isinstance(raw, dict):
            # A file containing e.g. `[]` or `null` decodes fine but has no
            # .items() -- treat any non-mapping shape as "no incidents".
            return {}
        out: dict[int, IncidentRecord] = {}
        for key, value in raw.items():
            try:
                out[int(key)] = IncidentRecord(**value)
            except (TypeError, ValueError):
                continue
        return out

    def _write(self, data: dict[int, IncidentRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({str(k): asdict(v) for k, v in data.items()}, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def add(self, record: IncidentRecord) -> None:
        data = self.load()
        data[record.message_id] = record
        self._write(data)

    def remove(self, message_id: int) -> None:
        data = self.load()
        if data.pop(message_id, None) is not None:
            self._write(data)

    def remove_by_service(self, service: str) -> int:
        """Delete every record whose service matches (case-insensitively).

        Used when a service is announced restored via /up, so a closed
        incident's buttons don't get revived with a fabricated duration on
        the next restart. Returns the number of records removed.
        """
        data = self.load()
        target = service.lower()
        matching = [mid for mid, rec in data.items() if rec.service.lower() == target]
        if not matching:
            return 0
        for mid in matching:
            del data[mid]
        self._write(data)
        return len(matching)


incident_store = IncidentStore()
