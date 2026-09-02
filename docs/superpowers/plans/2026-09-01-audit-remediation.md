# FenrirBot Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven correctness bugs, lock every command except `/ping` to administrators, harden the image, and correct the three drifted doc files found by the 2026-09-01 audit.

**Architecture:** Small, surgical changes to an existing `discord.py` cog-based bot. Pure logic is extracted into testable helpers (`src/utils/helpers.py`, `src/utils/incidents.py`, `src/utils/permissions.py`) so the fixes can be tested without a Discord connection — the existing `tests/server_config/` suite already uses this pattern with dataclass fakes, and we follow it rather than introducing mocks of `discord.Client`.

**Tech Stack:** Python 3.12, discord.py 2.7.1, docker-py 7.2.0, aiohttp 3.14.3, pydantic 2.13.4, pytest 9.1.1, ruff (CI only).

## Global Constraints

- **Branch and PR:** all work on `fix/audit-2026-09-01`, PR into **`dev`** (not `main`). Never commit directly to `dev`.
- **Git identity:** commit with `git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit ...`. Never modify global git config.
- **Language convention:** Discord-facing strings in **French**; Python code, comments and docstrings in **English**.
- **Run tests from the repo root** with `python3 -m pytest -q`. `pytest.ini` sets `pythonpath = .`, so `from src...` imports work without installation.
- **Baseline:** 13 tests pass at `49bce1d`. Never let the suite go red between commits.
- **No new runtime dependencies.** Everything here uses the stdlib or already-pinned packages.
- **Do not touch `/srv/nebula/.env`** — it is operator-only, reads and writes. Any new config value goes in Infisical.
- **Timezone:** the container runs `TZ=Europe/Paris`. `PARIS_TZ` already exists in `src/utils/helpers.py` — use it, do not redefine it.

---

### Task 1: `/scheduled` must read the time as Paris wall-clock

**Files:**
- Modify: `src/utils/helpers.py` (add `parse_local_datetime`, `format_paris`)
- Modify: `src/cogs/downtime.py:462-463` and `:490`
- Create: `tests/test_helpers_time.py`

**Interfaces:**
- Consumes: `PARIS_TZ` from `src/utils/helpers.py` (already defined at `:17`).
- Produces: `parse_local_datetime(when: str) -> datetime` — returns a **timezone-aware UTC** datetime. Raises `ValueError` on a malformed string. `format_paris(dt: datetime, fmt: str) -> str` — renders an aware datetime in Paris local time.

- [ ] **Step 1: Write the failing test**

Create `tests/test_helpers_time.py`:

```python
from datetime import datetime, timezone

import pytest

from src.utils.helpers import parse_local_datetime, format_paris


def test_summer_input_is_utc_plus_two():
    # 2026-09-05 is CEST (UTC+2): 22:00 Paris == 20:00 UTC
    assert parse_local_datetime("2026-09-05 22:00") == datetime(
        2026, 9, 5, 20, 0, tzinfo=timezone.utc
    )


def test_winter_input_is_utc_plus_one():
    # 2026-01-15 is CET (UTC+1): 22:00 Paris == 21:00 UTC
    assert parse_local_datetime("2026-01-15 22:00") == datetime(
        2026, 1, 15, 21, 0, tzinfo=timezone.utc
    )


def test_result_is_timezone_aware():
    assert parse_local_datetime("2026-09-05 22:00").tzinfo is not None


def test_malformed_input_raises_value_error():
    with pytest.raises(ValueError):
        parse_local_datetime("pas une date")


def test_format_paris_renders_local_wall_clock():
    utc = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
    assert format_paris(utc, "%H:%M") == "22:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_helpers_time.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_local_datetime' from 'src.utils.helpers'`

- [ ] **Step 3: Write minimal implementation**

In `src/utils/helpers.py`, add to the "Time & Duration Helpers" section (after `format_timestamp`, around `:246`):

```python
def parse_local_datetime(when: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' as Paris wall-clock time; return an aware UTC datetime.

    The bot runs with TZ=Europe/Paris and users type local time. Storing UTC keeps
    the JSON round-trip and the `<t:...>` Discord timestamps unambiguous.
    """
    naive = datetime.strptime(when, "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=PARIS_TZ).astimezone(timezone.utc)


def format_paris(dt: datetime, fmt: str) -> str:
    """Render an aware datetime in Paris local time."""
    return dt.astimezone(PARIS_TZ).strftime(fmt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_helpers_time.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Wire it into the cog**

In `src/cogs/downtime.py`, extend the import at `:15`:

```python
from ..utils.helpers import (
    get_announcement_channel,
    get_notification_mention,
    parse_local_datetime,
    format_paris,
)
```

Replace `:462-463`:

```python
        try:
            scheduled_time = datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
```

with:

```python
        try:
            scheduled_time = parse_local_datetime(when)
        except ValueError:
```

Replace `:490`:

```python
        when_display = scheduled_time.strftime("%A %d %B %Y à %H:%M")
```

with:

```python
        # scheduled_time is UTC; the user typed Paris local, so render it back in Paris
        when_display = format_paris(scheduled_time, "%A %d %B %Y à %H:%M")
```

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 18 passed

- [ ] **Step 7: Commit**

```bash
git add src/utils/helpers.py src/cogs/downtime.py tests/test_helpers_time.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "fix(downtime): parse /scheduled times as Paris local, not UTC

The container runs TZ=Europe/Paris but strptime results were stamped UTC
with no conversion, so every scheduled maintenance fired two hours late in
summer. The confirmation embed hid it by echoing the time back with strftime
on the same UTC object while the <t:...:F> field beside it rendered the real
(wrong) instant."
```

---

### Task 2: The scheduler must survive a bad entry and stop dropping maintenances silently

**Files:**
- Modify: `src/utils/embeds.py:72-102` (tolerate a missing author)
- Modify: `src/cogs/downtime.py:102-160`
- Create: `tests/test_embeds_author.py`

**Interfaces:**
- Consumes: `parse_local_datetime` from Task 1 (unchanged here).
- Produces: `DowntimeEmbed.maintenance(...)` now accepts `author: discord.User | discord.Member | None`. `DowntimeCog._trigger_scheduled_downtime(...) -> bool` — returns `True` only if the announcement was actually sent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_embeds_author.py`:

```python
from src.utils.embeds import DowntimeEmbed, ServiceType, MaintenanceType


class FakeAuthor:
    display_name = "Spifuth"


def test_footer_uses_author_display_name():
    embed = DowntimeEmbed.maintenance(
        "traefik", "patch", "30 minutes", FakeAuthor(),
        ServiceType.CONTAINER, MaintenanceType.SECURITY,
    )
    assert "Spifuth" in embed.footer.text


def test_footer_falls_back_when_author_is_none():
    embed = DowntimeEmbed.maintenance(
        "traefik", "patch", "30 minutes", None,
        ServiceType.CONTAINER, MaintenanceType.SECURITY,
    )
    assert embed.footer.text == "Fenrir · Maintenance · inconnu"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_embeds_author.py -v`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'display_name'` on the second test

- [ ] **Step 3: Write minimal implementation**

In `src/utils/embeds.py`, add above `class DowntimeEmbed` (after `_bar`, around `:76`):

```python
def _author_name(author: "discord.User | discord.Member | None") -> str:
    """Footer name for an author that may no longer be resolvable."""
    return author.display_name if author is not None else "inconnu"
```

Change the `maintenance` signature at `:85` from:

```python
        author: discord.User | discord.Member,
```

to:

```python
        author: discord.User | discord.Member | None,
```

and its footer at `:101` from:

```python
        embed.set_footer(text=f"Fenrir · Maintenance · {author.display_name}")
```

to:

```python
        embed.set_footer(text=f"Fenrir · Maintenance · {_author_name(author)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_embeds_author.py -v`
Expected: PASS — 2 passed

- [ ] **Step 5: Make the trigger report success, and never let one entry kill the loop**

In `src/cogs/downtime.py`, replace the loop body at `:108-117`:

```python
        for maintenance in self._scheduled_maintenances[:]:
            if maintenance.announced:
                continue

            if now >= maintenance.scheduled_time:
                # Check if it's a catchup (more than 5 minutes late)
                is_catchup = (now - maintenance.scheduled_time).total_seconds() > 300
                await self._trigger_scheduled_downtime(maintenance, is_catchup=is_catchup)
                maintenance.announced = True
                triggered_any = True
```

with:

```python
        for maintenance in self._scheduled_maintenances[:]:
            if maintenance.announced:
                continue

            if now >= maintenance.scheduled_time:
                # Check if it's a catchup (more than 5 minutes late)
                is_catchup = (now - maintenance.scheduled_time).total_seconds() > 300
                try:
                    sent = await self._trigger_scheduled_downtime(maintenance, is_catchup=is_catchup)
                except Exception as e:
                    # One bad entry must never end the loop — tasks.loop stops on an
                    # unhandled exception, which would silence every future maintenance.
                    print(f"[Downtime] Trigger failed for {maintenance.service}: {e!r}")
                    continue
                if not sent:
                    # Keep it queued rather than deleting it unannounced.
                    continue
                maintenance.announced = True
                triggered_any = True
```

Apply the same guard in `_catchup_missed_maintenances` at `:142-144`:

```python
            for maintenance in missed:
                await self._trigger_scheduled_downtime(maintenance, is_catchup=True)
                maintenance.announced = True
```

becomes:

```python
            for maintenance in missed:
                try:
                    sent = await self._trigger_scheduled_downtime(maintenance, is_catchup=True)
                except Exception as e:
                    print(f"[Downtime] Catchup failed for {maintenance.service}: {e!r}")
                    continue
                if sent:
                    maintenance.announced = True
```

- [ ] **Step 6: Make the trigger resolve the author safely and return a bool**

In `src/cogs/downtime.py`, replace `:153-161`:

```python
    async def _trigger_scheduled_downtime(self, maintenance: ScheduledMaintenance, is_catchup: bool = False):
        """Trigger the downtime announcement for a scheduled maintenance"""
        channel = self.bot.get_channel(maintenance.channel_id)
        if not channel:
            return

        author = self.bot.get_user(maintenance.author_id)
        assert author is not None
        service_type = self._get_service_type(maintenance.service)
```

with:

```python
    async def _trigger_scheduled_downtime(
        self, maintenance: ScheduledMaintenance, is_catchup: bool = False
    ) -> bool:
        """Announce a scheduled maintenance. Returns True only if it was sent."""
        channel = self.bot.get_channel(maintenance.channel_id)
        if not isinstance(channel, discord.TextChannel):
            print(
                f"[Downtime] Channel {maintenance.channel_id} unavailable for "
                f"{maintenance.service}; leaving it queued"
            )
            return False

        # get_user only reads the cache; fall back to the API, and tolerate a
        # user who has left. The embed renders "inconnu" rather than crashing.
        author = self.bot.get_user(maintenance.author_id)
        if author is None:
            try:
                author = await self.bot.fetch_user(maintenance.author_id)
            except discord.HTTPException:
                author = None
        service_type = self._get_service_type(maintenance.service)
```

Then at the end of the same method, replace `:223`:

```python
        await view.start_timer()
```

with:

```python
        await view.start_timer()
        return True
```

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 20 passed

- [ ] **Step 8: Commit**

```bash
git add src/utils/embeds.py src/cogs/downtime.py tests/test_embeds_author.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "fix(downtime): scheduler survives bad entries and stops dropping them

A bare 'assert author is not None' on a cache miss raised inside a
tasks.loop, which ends the loop — every future maintenance stopped firing
until restart. And a deleted target channel made the trigger return early
while the caller marked it announced anyway, deleting the maintenance
without announcing it. Now: fetch_user fallback, per-entry try/except, and
announced is only set on a confirmed send."
```

---

### Task 3: Docker reads must be sparse, race-tolerant and off the event loop

**Files:**
- Modify: `src/utils/docker.py` (whole `DockerManager`)
- Modify: `src/cogs/docker.py:20-29`, `:129-140`
- Create: `tests/test_docker_manager.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ContainerInfo` gains a `stack: str = ""` field. `DockerManager.get_stacks() -> list[str]` becomes a **pure cache read** (no API call). New `async DockerManager.refresh_async() -> list[ContainerInfo]` wraps the blocking `refresh()` in `asyncio.to_thread`.

**Background the implementer needs:** `docker-py`'s `containers.list(all=True)` defaults to `sparse=False`, which issues one `GET /containers/<id>/json` per container — 91 calls on this host — and raises `NotFound` if any container disappears mid-iteration, aborting the whole refresh. With `sparse=True` you get one call, but **`c.name` returns `None` and `c.labels` raises `DockerException`** — both were verified live on 2026-09-01. Read `c.attrs` directly instead. The sparse `attrs` keys are `Id, Names, Image, ImageID, State, Status, Labels, Command, Created, HostConfig, Mounts, NetworkSettings, Ports, Health`, where `State` is the plain string `"running"` and `Status` is `"Up 20 minutes (healthy)"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_docker_manager.py`:

```python
import json

from src.utils.docker import ContainerCache, ContainerInfo, DockerManager


class FakeSparseContainer:
    """Mimics a docker-py Container returned by list(sparse=True)."""

    def __init__(self, name, image, state, stack):
        self.short_id = "abc123def456"
        self.attrs = {
            "Names": [f"/{name}"],
            "Image": image,
            "State": state,
            "Status": "Up 2 hours" if state == "running" else "Exited (0)",
            "Labels": {"com.docker.compose.project": stack} if stack else {},
        }

    @property
    def name(self):  # docker-py returns None for sparse objects
        return None

    @property
    def labels(self):
        raise Exception("Label data is not available for sparse objects")


class FakeClient:
    def __init__(self, containers):
        self._containers = containers
        self.calls = 0

    class _Collection:
        def __init__(self, outer):
            self.outer = outer

        def list(self, all=False, sparse=False):
            assert sparse is True, "must request a sparse listing to avoid N+1 inspects"
            self.outer.calls += 1
            return self.outer._containers

    @property
    def containers(self):
        return FakeClient._Collection(self)


def _manager(tmp_path, containers):
    mgr = DockerManager.__new__(DockerManager)
    mgr.cache = None
    mgr._client = FakeClient(containers)
    mgr._data_file = tmp_path / "containers.json"
    return mgr


def test_refresh_reads_attrs_not_name_or_labels(tmp_path):
    mgr = _manager(tmp_path, [FakeSparseContainer("traefik", "traefik:v3", "running", "core")])
    out = mgr.refresh()
    assert out[0].name == "traefik"
    assert out[0].image == "traefik:v3"
    assert out[0].state == "running"
    assert out[0].stack == "core"


def test_get_stacks_reads_cache_and_makes_no_api_call(tmp_path):
    mgr = _manager(
        tmp_path,
        [
            FakeSparseContainer("traefik", "traefik:v3", "running", "core"),
            FakeSparseContainer("fenrirbot", "fenrirbot:latest", "running", "management"),
            FakeSparseContainer("orphan", "busybox", "exited", ""),
        ],
    )
    mgr.refresh()
    calls_after_refresh = mgr._client.calls
    assert mgr.get_stacks() == ["core", "management"]
    assert mgr._client.calls == calls_after_refresh, "get_stacks must not hit the API"


def test_cache_survives_a_json_file_without_the_stack_field(tmp_path):
    p = tmp_path / "containers.json"
    p.write_text(json.dumps({
        "containers": [{"id": "a", "name": "old", "image": "i", "status": "s", "state": "running"}],
        "last_updated": "2026-01-01T00:00:00",
    }))
    cache = ContainerCache.from_dict(json.loads(p.read_text()))
    assert cache.containers[0].stack == ""


def test_refresh_keeps_going_when_one_container_vanishes(tmp_path):
    class Vanishing(FakeSparseContainer):
        @property
        def attrs(self):
            raise KeyError("Names")

        @attrs.setter
        def attrs(self, value):
            pass

    good = FakeSparseContainer("traefik", "traefik:v3", "running", "core")
    mgr = _manager(tmp_path, [Vanishing("gone", "x", "running", ""), good])
    out = mgr.refresh()
    assert [c.name for c in out] == ["traefik"]
    assert mgr.cache is not None, "a single bad container must not abandon the whole refresh"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_docker_manager.py -v`
Expected: FAIL — `TypeError: ContainerInfo.__init__() got an unexpected keyword argument 'stack'` / `AssertionError: must request a sparse listing`

- [ ] **Step 3: Write the implementation**

Replace `src/utils/docker.py` entirely with:

```python
"""Docker container discovery and caching"""

import asyncio
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

try:
    import docker
    HAS_DOCKER_SDK = True
except ImportError:
    HAS_DOCKER_SDK = False


DATA_FILE = Path(__file__).parent.parent.parent / "data" / "containers.json"


@dataclass
class ContainerInfo:
    """Container information"""
    id: str
    name: str
    image: str
    status: str
    state: str  # running, exited, paused, etc.
    stack: str = ""  # com.docker.compose.project label, "" if not composed

    @property
    def display_name(self) -> str:
        """Friendly display name for Discord"""
        return self.name.lstrip("/")


@dataclass
class ContainerCache:
    """Cached container data"""
    containers: list[ContainerInfo]
    last_updated: str

    def to_dict(self) -> dict:
        return {
            "containers": [asdict(c) for c in self.containers],
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerCache":
        containers = [ContainerInfo(**c) for c in data.get("containers", [])]
        return cls(containers=containers, last_updated=data.get("last_updated", ""))


class DockerManager:
    """Manages Docker container discovery and caching via docker-py SDK"""

    def __init__(self):
        self.cache: Optional[ContainerCache] = None
        self._client: Optional["docker.DockerClient"] = None
        self._data_file = DATA_FILE
        self._load_cache()

    def _get_client(self) -> Optional["docker.DockerClient"]:
        """Lazily initialize the Docker client (reads DOCKER_HOST env var)"""
        if not HAS_DOCKER_SDK:
            print("⚠️ docker-py not installed. Run: pip install docker")
            return None
        if self._client is None:
            try:
                self._client = docker.from_env()
            except Exception as e:
                print(f"⚠️ Docker client unavailable: {e}")
                return None
        return self._client

    def _load_cache(self):
        """Load cached container data from file"""
        if self._data_file.exists():
            try:
                with open(self._data_file, "r") as f:
                    data = json.load(f)
                    self.cache = ContainerCache.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                self.cache = None

    def _save_cache(self):
        """Save container data to cache file (atomic: write temp, then replace)"""
        if not self.cache:
            return
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._data_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.cache.to_dict(), f, indent=2)
        tmp.replace(self._data_file)

    def refresh(self) -> list[ContainerInfo]:
        """Refresh container list from the Docker daemon.

        Uses sparse=True: one API call instead of 1+N inspects, and immune to a
        container being removed mid-iteration. Sparse objects do NOT populate
        `.name` (returns None) or `.labels` (raises), so read `.attrs` directly.
        """
        client = self._get_client()
        if client is None:
            return []

        try:
            raw = client.containers.list(all=True, sparse=True)
        except Exception as e:
            print(f"⚠️ Docker refresh failed: {e}")
            return []

        containers = []
        for c in raw:
            try:
                attrs = c.attrs
                names = attrs.get("Names") or []
                name = names[0].lstrip("/") if names else attrs.get("Id", "")[:12]
                containers.append(ContainerInfo(
                    id=c.short_id,
                    name=name,
                    image=attrs.get("Image", ""),
                    status=attrs.get("Status", ""),
                    state=attrs.get("State", ""),
                    stack=(attrs.get("Labels") or {}).get("com.docker.compose.project", ""),
                ))
            except Exception as e:
                # One malformed or vanished entry must not abandon the whole refresh.
                print(f"⚠️ Skipping a container during refresh: {e!r}")
                continue

        self.cache = ContainerCache(
            containers=containers,
            last_updated=datetime.now().isoformat()
        )
        self._save_cache()
        return containers

    async def refresh_async(self) -> list[ContainerInfo]:
        """Run the blocking refresh off the event loop."""
        return await asyncio.to_thread(self.refresh)

    def get_containers(self, include_stopped: bool = True) -> list[ContainerInfo]:
        """Get list of containers from cache. Never blocks; never calls the API."""
        if not self.cache:
            return []

        if include_stopped:
            return self.cache.containers
        return [c for c in self.cache.containers if c.state == "running"]

    def get_container_names(self, include_stopped: bool = True) -> list[str]:
        """Get list of container names for autocomplete"""
        return [c.display_name for c in self.get_containers(include_stopped)]

    def get_stacks(self) -> list[str]:
        """Unique Compose stack names, read from the cache. No API call."""
        return sorted({c.stack for c in self.get_containers(True) if c.stack})


# Global instance
docker_manager = DockerManager()
```

> Note the deliberate behaviour change in `get_containers`: it no longer self-refreshes on a cache miss. Refresh is owned by the `docker` cog's `tasks.loop`, which runs once at startup and every 5 minutes — an autocomplete handler must never trigger a blocking API call.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_docker_manager.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Move the cog's refresh calls off the event loop**

In `src/cogs/docker.py`, replace `:20-29`:

```python
    @tasks.loop(minutes=5)
    async def auto_refresh(self):
        """Auto-refresh container list every 5 minutes"""
        docker_manager.refresh()

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()
        # Initial refresh on startup
        docker_manager.refresh()
```

with:

```python
    @tasks.loop(minutes=5)
    async def auto_refresh(self):
        """Auto-refresh container list every 5 minutes"""
        await docker_manager.refresh_async()

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()
        # Initial refresh on startup
        await docker_manager.refresh_async()
```

And replace `:134` inside `refresh_slash`:

```python
        containers = docker_manager.refresh()
```

with:

```python
        containers = await docker_manager.refresh_async()
```

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 25 passed

- [ ] **Step 7: Commit**

```bash
git add src/utils/docker.py src/cogs/docker.py tests/test_docker_manager.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "perf(docker): sparse listing, race-tolerant refresh, off the event loop

containers.list(all=True) defaulted to sparse=False, issuing 1+90 sequential
inspects against socket-proxy from inside async autocomplete handlers, and
aborting the whole refresh with a 404 whenever a container vanished
mid-iteration (observed live). Now one sparse call, per-container error
isolation, atomic cache writes, and stacks derived from the cache so
autocomplete costs zero API calls."
```

---

### Task 4: Incident buttons must survive a restart

**Files:**
- Create: `src/utils/incidents.py`
- Modify: `src/utils/views.py`
- Modify: `src/cogs/downtime.py` (register incidents on send)
- Modify: `src/bot.py` (rehydrate on startup)
- Create: `tests/test_incidents.py`

**Interfaces:**
- Consumes: `ServiceType`, `MaintenanceType` from `src/utils/embeds.py`.
- Produces: `IncidentStore` with `load() -> dict[int, IncidentRecord]`, `add(record)`, `remove(message_id)`. `IncidentRecord` dataclass with fields `message_id, channel_id, service, author_id, duration_str, service_type, maintenance_type`. `DowntimeView` gains `timeout=None`, stable `custom_id`s, and `DowntimeView.from_record(record, store) -> DowntimeView`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_incidents.py`:

```python
import json

import pytest

from src.utils.incidents import IncidentRecord, IncidentStore


@pytest.fixture
def store(tmp_path):
    return IncidentStore(path=tmp_path / "open_incidents.json")


def _record(message_id=111):
    return IncidentRecord(
        message_id=message_id,
        channel_id=222,
        service="traefik",
        author_id=333,
        duration_str="30 minutes",
        service_type="container",
        maintenance_type="security",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_incidents.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.incidents'`

- [ ] **Step 3: Write the implementation**

Create `src/utils/incidents.py`:

```python
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


class IncidentStore:
    """A tiny JSON-backed map of message_id -> IncidentRecord."""

    def __init__(self, path: Path = STORE_FILE):
        self.path = Path(path)

    def load(self) -> dict[int, IncidentRecord]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
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


incident_store = IncidentStore()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_incidents.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Make the view persistent**

In `src/utils/views.py`, replace the import block and `__init__` (`:1-72`):

```python
"""Interactive views (buttons, modals) for Fenrir Bot"""

import discord
from discord import ui
from datetime import datetime, timedelta
import asyncio
import re

from .embeds import DowntimeEmbed, MaintenanceType, ServiceType
from .incidents import IncidentRecord, IncidentStore, incident_store
```

and change `super().__init__(timeout=86400)` at `:49` to `super().__init__(timeout=None)`, adding a `store` parameter:

```python
    def __init__(
        self,
        service: str,
        author_id: int,
        duration_str: str = "Unknown",
        announcement_channel: discord.abc.Messageable | None = None,
        notification_mention: str | None = "@here",
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: MaintenanceType = MaintenanceType.DOWNTIME,
        store: IncidentStore | None = None,
    ):
        # timeout=None + stable custom_ids => discord.py treats this as a
        # persistent view, so bot.add_view() can revive it after a restart.
        super().__init__(timeout=None)
        self.store = store or incident_store
```

Give the buttons stable ids — replace the two decorators at `:97` and `:154`:

```python
    @ui.button(label="✅ Service Restored", style=discord.ButtonStyle.green,
               custom_id="fenrir:incident:restore")
```

```python
    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.red,
               custom_id="fenrir:incident:cancel")
```

Add the rehydration constructor at the end of the class, after `on_timeout`:

```python
    @classmethod
    def from_record(cls, record: IncidentRecord, store: IncidentStore) -> "DowntimeView":
        """Rebuild a view from disk after a restart."""
        try:
            service_type = ServiceType(record.service_type)
        except ValueError:
            service_type = ServiceType.OTHER
        try:
            maintenance_type = MaintenanceType(record.maintenance_type)
        except ValueError:
            maintenance_type = MaintenanceType.DOWNTIME
        return cls(
            service=record.service,
            author_id=record.author_id,
            duration_str=record.duration_str,
            service_type=service_type,
            maintenance_type=maintenance_type,
            store=store,
        )
```

- [ ] **Step 6: Defer first, and clear the record when the incident closes**

In `restore_button`, insert immediately after the author check (before `self.resolved = True` at `:107`):

```python
        # Four REST calls follow; Discord's initial-response deadline is 3s.
        await interaction.response.defer(ephemeral=True)
```

and replace the final response at `:147-150`:

```python
        await interaction.response.send_message(
            f"✅ **{self.service}** marked as restored!",
            ephemeral=True
        )
```

with:

```python
        if interaction.message is not None:
            self.store.remove(interaction.message.id)

        await interaction.followup.send(
            f"✅ **{self.service}** marked as restored!",
            ephemeral=True
        )
```

In `cancel_button`, insert the same `defer` after its author check (before `:164`):

```python
        await interaction.response.defer(ephemeral=True)
```

and replace `:178-181`:

```python
        await interaction.response.send_message(
            f"🚫 Downtime announcement for **{self.service}** has been cancelled.",
            ephemeral=True
        )
```

with:

```python
        if interaction.message is not None:
            self.store.remove(interaction.message.id)

        await interaction.followup.send(
            f"🚫 Downtime announcement for **{self.service}** has been cancelled.",
            ephemeral=True
        )
```

- [ ] **Step 7: Record incidents when they are announced**

In `src/cogs/downtime.py`, extend the imports at `:14`:

```python
from ..utils.views import DowntimeView
from ..utils.incidents import IncidentRecord, incident_store
```

In `maintenance_slash`, after `view.message = msg` (`:402`), add:

```python
        incident_store.add(IncidentRecord(
            message_id=msg.id,
            channel_id=channel.id,
            service=service,
            author_id=interaction.user.id,
            duration_str=duration,
            service_type=svc_type.value,
            maintenance_type=maint_type.value,
        ))
```

In `_trigger_scheduled_downtime`, after `view.message = msg` (`:202`), add:

```python
        incident_store.add(IncidentRecord(
            message_id=msg.id,
            channel_id=channel.id,
            service=maintenance.service,
            author_id=maintenance.author_id,
            duration_str=maintenance.duration,
            service_type=service_type.value,
            maintenance_type=maint_type.value,
        ))
```

- [ ] **Step 8: Rehydrate on startup**

In `src/bot.py`, extend the imports at `:8`:

```python
from .utils.webhook_server import WebhookServer
from .utils.incidents import incident_store
from .utils.views import DowntimeView
```

and append to `setup_hook`, after the command sync block (`:59`):

```python
        # Revive the buttons on any incident that was still open at shutdown.
        revived = 0
        for record in incident_store.load().values():
            try:
                self.add_view(DowntimeView.from_record(record, incident_store),
                              message_id=record.message_id)
                revived += 1
            except Exception as e:
                print(f"  ⚠️ Could not revive incident {record.message_id}: {e!r}")
        if revived:
            print(f"  ✅ Revived {revived} open incident view(s)")
```

- [ ] **Step 9: Ignore the new state file**

Append to `.gitignore` under the "Runtime data" block (after `data/server_config_state.json`):

```
data/open_incidents.json
```

- [ ] **Step 10: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 31 passed

- [ ] **Step 11: Commit**

```bash
git add src/utils/incidents.py src/utils/views.py src/cogs/downtime.py src/bot.py .gitignore tests/test_incidents.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "fix(views): persist open incidents so buttons survive a restart

DowntimeView was an in-memory view with no custom_ids, so every deploy left
the Service restauré / Annuler buttons dead on any open announcement.
Incidents are now recorded in data/open_incidents.json and re-registered via
bot.add_view() at startup. Both handlers also defer() before their four REST
calls, which were racing Discord's 3s initial-response deadline."
```

---

### Task 5: `/alerts` must not report all-clear when Grafana is unreachable

**Files:**
- Modify: `src/utils/grafana.py:16-32`
- Modify: `src/cogs/alerts.py:81-92`
- Create: `tests/test_grafana_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `GrafanaClient.get_active_alerts() -> list[dict] | None` — `None` means "could not determine", `[]` means "genuinely no alerts".

- [ ] **Step 1: Write the failing test**

Create `tests/test_grafana_client.py`:

```python
import asyncio

import pytest

from src.utils.grafana import GrafanaClient


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or []

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises

    def get(self, *a, **kw):
        if self._raises:
            raise self._raises
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _run(client, monkeypatch, session):
    monkeypatch.setattr("src.utils.grafana.aiohttp.ClientSession", lambda **kw: session)
    return asyncio.run(client.get_active_alerts())


def test_returns_list_on_success(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    payload = [{"labels": {"alertname": "HighCPU"}}]
    result = _run(client, monkeypatch, FakeSession(FakeResponse(200, payload)))
    assert result == payload


def test_empty_list_means_genuinely_no_alerts(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    result = _run(client, monkeypatch, FakeSession(FakeResponse(200, [])))
    assert result == []


def test_returns_none_on_auth_failure(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "bad-token")
    result = _run(client, monkeypatch, FakeSession(FakeResponse(401)))
    assert result is None, "401 must not look like 'no alerts'"


def test_returns_none_when_unreachable(monkeypatch):
    client = GrafanaClient("http://grafana:3000", "token")
    result = _run(client, monkeypatch, FakeSession(raises=OSError("connection refused")))
    assert result is None, "a dead API must not look like 'no alerts'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_grafana_client.py -v`
Expected: FAIL — the last two tests fail with `assert [] is None`

- [ ] **Step 3: Write the implementation**

In `src/utils/grafana.py`, replace `get_active_alerts` (`:16-32`):

```python
    async def get_active_alerts(self) -> list[dict] | None:
        """
        Fetch currently firing alerts from Grafana Alertmanager.

        Returns the alert list on success (possibly empty), or **None** if the
        result could not be determined — a dead API or a rejected token must
        never render as "no alerts", which is an all-clear the caller cannot
        distinguish from a real one.
        """
        url = f"{self.base_url}/api/alertmanager/grafana/api/v2/alerts"
        params = {"active": "true", "silenced": "false", "inhibited": "false"}
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        print(f"⚠️ Grafana returned {resp.status} for {url}")
                        return None
                    return await resp.json()
        except Exception as e:
            print(f"⚠️ Grafana unreachable: {e!r}")
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_grafana_client.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Make the cog say so**

In `src/cogs/alerts.py`, replace `:81-92`:

```python
        alerts = await self.grafana.get_active_alerts()

        if not alerts:
            embed = discord.Embed(
                title="Aucune alerte",
                description="Tous les systèmes sont opérationnels.",
                color=0x2C2F33,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Fenrir · Grafana")
            await interaction.followup.send(embed=embed)
            return
```

with:

```python
        alerts = await self.grafana.get_active_alerts()

        if alerts is None:
            embed = discord.Embed(
                title="Statut inconnu",
                description=(
                    "Impossible de joindre Grafana — ce n'est **pas** un tout-va-bien. "
                    "Vérifie `GRAFANA_URL` / `GRAFANA_API_KEY` et que le conteneur répond."
                ),
                color=0x2C2F33,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Fenrir · Grafana injoignable")
            await interaction.followup.send(embed=embed)
            return

        if not alerts:
            embed = discord.Embed(
                title="Aucune alerte",
                description="Tous les systèmes sont opérationnels.",
                color=0x2C2F33,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Fenrir · Grafana")
            await interaction.followup.send(embed=embed)
            return
```

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 35 passed

- [ ] **Step 7: Commit**

```bash
git add src/utils/grafana.py src/cogs/alerts.py tests/test_grafana_client.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "fix(alerts): distinguish 'no alerts' from 'cannot reach Grafana'

get_active_alerts caught everything and returned [], so a dead API and a
rejected token both rendered the green all-clear embed — a monitoring
surface reporting healthy because it is broken. Returns None on failure now,
and the cog says the status is unknown."
```

---

### Task 6: `/server-config` must not wipe category overwrites, and its diff must be honest

**Files:**
- Modify: `src/server_config/applier.py:149-172`
- Modify: `src/server_config/differ.py:95-108`
- Modify: `src/server_config/reports.py:30-42`
- Create: `tests/server_config/test_applier_overwrites.py`
- Modify: `tests/server_config/test_differ.py` (append)

**Interfaces:**
- Consumes: `CategorySpec`, `ChannelSpec` from `src/server_config/models.py`.
- Produces: `ChannelDiff.to_edit` is now populated as `list[tuple[CategorySpec, ChannelSpec]]`. `summary_from_diffs` sets `channels_edited`.

**Background the implementer needs:** discord.py guards the argument with `if overwrites is not None` (`discord/abc.py:531`). An **empty dict is not None**, so it serialises to `permission_overwrites: []` and deletes every overwrite on the channel or category. `apply_channels` already guards with `if ch_overwrites:` (`:206`); `apply_categories` does not.

- [ ] **Step 1: Write the failing test**

Create `tests/server_config/test_applier_overwrites.py`:

```python
import asyncio
from dataclasses import dataclass, field

from src.server_config.applier import ApplyContext, apply_categories
from src.server_config.models import CategorySpec, OverwriteSpec, Spec
from src.server_config.reports import Summary
from src.server_config.resolver import Resolver


@dataclass
class FakeCategory:
    name: str
    position: int = 0
    edit_calls: list = field(default_factory=list)

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs)


@dataclass
class FakeRole:
    name: str
    id: int = 1

    def is_default(self):
        return self.name == "@everyone"


@dataclass
class FakeGuild:
    categories: list = field(default_factory=list)
    roles: list = field(default_factory=list)

    @property
    def default_role(self):
        return FakeRole("@everyone", id=0)


def _ctx(guild, spec):
    resolver = Resolver(guild=guild, spec=spec)
    return ApplyContext(bot=None, guild=guild, spec=spec, resolver=resolver,
                        summary=Summary(), dry_run=False)


def _spec(categories):
    return Spec.model_construct(
        meta=None, server=None, roles=[], categories=categories,
        webhooks=[], reaction_roles=[],
    )


def test_category_without_overwrites_is_never_edited_with_an_empty_dict():
    existing = FakeCategory(name="General", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(id="c1", name="General", position=0, overwrites=[], channels=[])
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    wiping = [c for c in existing.edit_calls if c.get("overwrites") == {}]
    assert wiping == [], "an empty overwrites dict deletes every overwrite on the category"


def test_category_with_overwrites_still_reconciles_them():
    existing = FakeCategory(name="Staff", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(
        id="c1", name="Staff", position=0,
        overwrites=[OverwriteSpec(target="@everyone", deny=["VIEW_CHANNEL"])],
        channels=[],
    )
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    assert any("overwrites" in c and c["overwrites"] for c in existing.edit_calls)


def test_partial_overwrites_from_an_unresolved_role_do_not_apply():
    existing = FakeCategory(name="Staff", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(
        id="c1", name="Staff", position=0,
        overwrites=[OverwriteSpec(target="missing_role", allow=["VIEW_CHANNEL"])],
        channels=[],
    )
    spec = _spec([cat])
    ctx = _ctx(guild, spec)

    asyncio.run(apply_categories(ctx))

    wiping = [c for c in existing.edit_calls if c.get("overwrites") == {}]
    assert wiping == [], "a role that failed to resolve must not strip the live overwrites"
    assert ctx.summary.errors, "the unresolved target must be reported"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/server_config/test_applier_overwrites.py -v`
Expected: FAIL — `test_category_without_overwrites_is_never_edited_with_an_empty_dict` and `test_partial_overwrites_from_an_unresolved_role_do_not_apply` both find a `{"overwrites": {}}` call

- [ ] **Step 3: Write the implementation**

In `src/server_config/applier.py`, replace `:149-172` (the whole `else` branch of `apply_categories`):

```python
        else:
            ctx.resolver.register_category(spec.id, existing)
            needs_edit = existing.position != spec.position
            if needs_edit:
                ctx.log(f"~ category: {spec.name} (position)")
                if not ctx.dry_run:
                    try:
                        await existing.edit(position=spec.position, overwrites=overwrites,
                                            reason="server_config apply")
                        ctx.summary.categories_edited += 1
                    except discord.Forbidden as e:
                        ctx.err(f"category edit forbidden: {spec.name} ({e})")
                    except discord.HTTPException as e:
                        ctx.err(f"category edit HTTP: {spec.name} ({e})")
                else:
                    ctx.summary.categories_edited += 1
            else:
                # Still reconcile overwrites silently if they drifted
                if not ctx.dry_run:
                    try:
                        await existing.edit(overwrites=overwrites, reason="server_config apply")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                ctx.summary.categories_unchanged += 1
```

with:

```python
        else:
            ctx.resolver.register_category(spec.id, existing)
            needs_edit = existing.position != spec.position
            # NEVER pass an empty dict: discord.py guards on `is not None`, so {}
            # serialises to permission_overwrites: [] and deletes every overwrite.
            # An empty dict here also means "a target failed to resolve", which is
            # exactly when wiping the live config is most destructive.
            can_set_overwrites = bool(overwrites)
            if needs_edit:
                ctx.log(f"~ category: {spec.name} (position)")
                if not ctx.dry_run:
                    kwargs = {"position": spec.position, "reason": "server_config apply"}
                    if can_set_overwrites:
                        kwargs["overwrites"] = overwrites
                    try:
                        await existing.edit(**kwargs)
                        ctx.summary.categories_edited += 1
                    except discord.Forbidden as e:
                        ctx.err(f"category edit forbidden: {spec.name} ({e})")
                    except discord.HTTPException as e:
                        ctx.err(f"category edit HTTP: {spec.name} ({e})")
                else:
                    ctx.summary.categories_edited += 1
            else:
                # Still reconcile overwrites if they drifted — but only real ones.
                if not ctx.dry_run and can_set_overwrites:
                    try:
                        await existing.edit(overwrites=overwrites, reason="server_config apply")
                    except (discord.Forbidden, discord.HTTPException) as e:
                        # Was a bare `pass` — a silent failure in the one place the
                        # report claims nothing happened.
                        ctx.err(f"category overwrite reconcile failed: {spec.name} ({e})")
                ctx.summary.categories_unchanged += 1
```

Also fix `_build_overwrites` at `:117-123` so an unresolved target is always reported, not only outside dry-run:

```python
    for ow in overwrites:
        target = ctx.resolver.resolve_target(ow.target)
        if target is None:
            ctx.err(f"overwrite target not found: {ow.target}")
            continue
        out[target] = to_permission_overwrite(allow=ow.allow, deny=ow.deny)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/server_config/test_applier_overwrites.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Write the failing test for the honest diff**

Append to `tests/server_config/test_differ.py`:

```python
from src.server_config.differ import diff_channels
from src.server_config.models import CategorySpec, ChannelSpec


@dataclass
class FakeChannel:
    name: str
    topic: str = ""
    slowmode_delay: int = 0


@dataclass
class FakeCategoryChannel:
    name: str
    position: int = 0
    channels: list = field(default_factory=list)


@dataclass
class FakeGuildWithCats:
    categories: list = field(default_factory=list)


def test_diff_channels_reports_a_topic_change_as_an_edit():
    live = FakeCategoryChannel(name="General", channels=[FakeChannel(name="main", topic="old")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="General", channels=[
        ChannelSpec(id="ch1", name="main", topic="new")
    ])

    diff = diff_channels(guild, [cat])

    assert len(diff.to_edit) == 1
    assert diff.to_edit[0][1].name == "main"
    assert diff.unchanged == []


def test_diff_channels_reports_a_match_as_unchanged():
    live = FakeCategoryChannel(name="General", channels=[FakeChannel(name="main", topic="same")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="General", channels=[
        ChannelSpec(id="ch1", name="main", topic="same")
    ])

    diff = diff_channels(guild, [cat])

    assert diff.to_edit == []
    assert len(diff.unchanged) == 1
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python3 -m pytest tests/server_config/test_differ.py -v`
Expected: FAIL — `assert 0 == 1`; `to_edit` is never populated

- [ ] **Step 7: Write the implementation**

In `src/server_config/differ.py`, replace `diff_channels` (`:95-108`):

```python
def diff_channels(guild: Any, categories: list[CategorySpec]) -> ChannelDiff:
    result = ChannelDiff()
    cats_by_name = {c.name: c for c in getattr(guild, "categories", [])}
    for cat_spec in categories:
        parent = cats_by_name.get(cat_spec.name)
        existing_children = list(getattr(parent, "channels", [])) if parent else []
        existing_by_name = {c.name: c for c in existing_children}
        for ch_spec in cat_spec.channels:
            existing = existing_by_name.get(ch_spec.name)
            if existing is None:
                result.to_create.append((cat_spec, ch_spec))
                continue
            # Mirror exactly what apply_channels reconciles, so the diff cannot
            # report "unchanged" for something apply will edit.
            changed = False
            if ch_spec.topic is not None and getattr(existing, "topic", None) != ch_spec.topic:
                changed = True
            if getattr(existing, "slowmode_delay", 0) != ch_spec.slowmode_delay:
                changed = True
            if hasattr(existing, "user_limit") and existing.user_limit != ch_spec.user_limit:
                changed = True
            if changed:
                result.to_edit.append((cat_spec, ch_spec))
            else:
                result.unchanged.append((cat_spec, ch_spec))
    return result
```

In `src/server_config/reports.py`, add the missing line to `summary_from_diffs` after `:40`:

```python
    s.channels_created = len(ch_diff.to_create)
    s.channels_edited = len(ch_diff.to_edit)
    s.channels_unchanged = len(ch_diff.unchanged)
```

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 40 passed

- [ ] **Step 9: Commit**

```bash
git add src/server_config/applier.py src/server_config/differ.py src/server_config/reports.py tests/server_config/
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "fix(server_config): never wipe category overwrites; make the diff honest

apply_categories passed overwrites= unconditionally. discord.py guards that
argument with 'is not None', so an empty dict — from a category with no
overwrites, or from a role that failed to resolve — serialised to
permission_overwrites: [] and deleted every overwrite, counted as
'unchanged' with the error swallowed by a bare pass. The channel path
already guarded this. Also populates ChannelDiff.to_edit so /server-config
diff stops reporting 0 modifiés for channels apply will edit."
```

---

### Task 7: Everything except `/ping` is administrator-only

**Files:**
- Create: `src/utils/permissions.py`
- Modify: `src/cogs/downtime.py`, `status.py`, `docker.py`, `dashboard.py`, `reports.py`, `alerts.py`, `server_config.py`
- Modify: `src/bot.py` (error handler)
- Create: `tests/test_permission_gate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `admin_only()` — a decorator applying **both** `app_commands.default_permissions(administrator=True)` (hides it in the Discord UI) and `app_commands.checks.has_permissions(administrator=True)` (enforces it at runtime, because the UI default is only a default a guild admin can override).

- [ ] **Step 1: Write the failing test**

Create `tests/test_permission_gate.py`:

```python
import importlib

import pytest
from discord import app_commands

from src.utils.permissions import admin_only

COGS = [
    "src.cogs.downtime",
    "src.cogs.status",
    "src.cogs.docker",
    "src.cogs.dashboard",
    "src.cogs.reports",
    "src.cogs.alerts",
]

# The only command a non-admin member keeps.
OPEN_COMMANDS = {"ping"}


def _commands_in(module_path):
    module = importlib.import_module(module_path)
    found = []
    for obj in vars(module).values():
        if not isinstance(obj, type):
            continue
        for attr in vars(obj).values():
            if isinstance(attr, app_commands.Command):
                found.append(attr)
    return found


def test_admin_only_sets_both_the_ui_default_and_a_runtime_check():
    @admin_only()
    @app_commands.command(name="probe", description="probe")
    async def probe(interaction):  # pragma: no cover - never invoked
        pass

    assert probe.default_permissions is not None
    assert probe.default_permissions.administrator is True
    assert probe.checks, "a UI default alone is overridable by a guild admin"


@pytest.mark.parametrize("module_path", COGS)
def test_every_command_except_ping_is_guarded(module_path):
    for command in _commands_in(module_path):
        if command.name in OPEN_COMMANDS:
            continue
        assert command.checks, f"/{command.name} has no runtime permission check"
        assert command.default_permissions is not None, f"/{command.name} has no UI default"


def test_ping_stays_open():
    ping = [c for c in _commands_in("src.cogs.status") if c.name == "ping"]
    assert ping, "ping command not found"
    assert not ping[0].checks, "/ping is meant to stay usable by everyone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_permission_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.permissions'`

- [ ] **Step 3: Write the gate**

Create `src/utils/permissions.py`:

```python
"""Command permission gates.

`default_permissions` only sets what Discord shows by default — a guild admin
can override it per-command in Server Settings → Integrations. Pairing it with
a real check means the override cannot silently reopen a command.
"""

from discord import app_commands


def admin_only():
    """Require Administrator, both in the Discord UI and at invocation time."""
    def decorator(command):
        command = app_commands.checks.has_permissions(administrator=True)(command)
        command = app_commands.default_permissions(administrator=True)(command)
        return command
    return decorator
```

- [ ] **Step 4: Apply it to every command except `/ping`**

Add the import to each of the six cog files:

```python
from ..utils.permissions import admin_only
```

Then place `@admin_only()` **directly below** each `@app_commands.command(...)` line (above any `@app_commands.describe`/`choices`/`autocomplete`), for these twelve:

- `src/cogs/downtime.py` — `up` (`:308`), `maintenance` (`:329`), `scheduled` (`:431`), `scheduled-list` (`:531`), `scheduled-cancel` (`:568`)
- `src/cogs/status.py` — `status` (`:17`). **Leave `ping` (`:33`) untouched.**
- `src/cogs/docker.py` — `containers` (`:69`), `stacks` (`:108`), `refresh` (`:129`)
- `src/cogs/dashboard.py` — `dashboard` (`:17`)
- `src/cogs/reports.py` — `rapport` (`:73`)
- `src/cogs/alerts.py` — `alerts` (`:70`)

Example, for `src/cogs/dashboard.py`:

```python
    @app_commands.command(name="dashboard", description="📊 Afficher le tableau de bord des services")
    @admin_only()
    async def dashboard_slash(self, interaction: discord.Interaction):
```

For the prefix command in `src/cogs/status.py:39`, add the `commands.ext` equivalent:

```python
    @commands.command(name="status")
    @commands.has_permissions(administrator=True)
    async def status_prefix(self, ctx: commands.Context, *, message: str):
```

In `src/cogs/server_config.py`, the five commands already carry `@app_commands.default_permissions(administrator=True)`. Replace each of those five decorator lines (`:42`, `:69`, `:110`, `:217`, `:235`) with `@admin_only()` and add the import, so they gain the runtime check too.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_permission_gate.py -v`
Expected: PASS — 8 passed

- [ ] **Step 6: Tell a denied user why**

In `src/bot.py`, add the import at `:5`:

```python
from discord import app_commands
```

and append this method to `FenrirBot`, after `setup_hook`:

```python
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Give a denied user a clear answer instead of a silent failure."""
        if isinstance(error, app_commands.MissingPermissions):
            message = "⛔ Cette commande est réservée aux administrateurs."
        else:
            print(f"⚠️ Command error in /{interaction.command.name if interaction.command else '?'}: {error!r}")
            message = "❌ Une erreur est survenue lors de l'exécution de cette commande."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
```

Wire it in `setup_hook`, before the sync block:

```python
        self.tree.on_error = self.on_app_command_error
```

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS — 48 passed

- [ ] **Step 8: Commit**

```bash
git add src/utils/permissions.py src/cogs/ src/bot.py tests/test_permission_gate.py
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "feat(security): restrict every command except /ping to administrators

Thirteen of fourteen commands had no guard: any guild member could @here the
room, post as the bot in the announcement channel, and enumerate all 90
containers, every stack, host CPU/RAM and every firing Grafana alert. The
gate pairs default_permissions (UI default) with has_permissions (runtime),
because the former alone is overridable per-command by a guild admin."
```

---

### Task 8: Non-root image, and stop shipping pytest to production

**Files:**
- Modify: `Dockerfile`
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: image runs as uid `10001`. **Host action required** — the bind mount `${DOCKERDIR}/appdata/fenrirbot/data` is currently root-owned and must be chowned before the new image can write to it. This is done in Task 10.

- [ ] **Step 1: Split the dependencies**

Replace `requirements.txt` with:

```
discord.py>=2.3.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
docker>=7.0.0
pydantic>=2.6.0
ruamel.yaml>=0.18.0
```

Create `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0.0
```

- [ ] **Step 2: Verify the test suite still installs and runs**

Run: `python3 -m pytest -q`
Expected: PASS — 48 passed (pytest is already installed in the dev environment; this confirms nothing imported it from the runtime list)

- [ ] **Step 3: Make the image non-root**

Replace `Dockerfile` with:

```dockerfile
# ═══════════════════════════════════════════════════════════════
# FENRIRBOT - Discord Bot
# Homelab monitoring and downtime announcements
# ═══════════════════════════════════════════════════════════════

FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY specs/ ./specs/
COPY run.py .

# Run as an unprivileged user. This process holds the Discord token and talks
# to socket-proxy, so it is the one container worth shrinking.
# NOTE: the host bind mount at ${DOCKERDIR}/appdata/fenrirbot/data must be
# chowned to 10001:10001 or the bot cannot persist scheduled maintenances.
RUN adduser -D -u 10001 fenrir \
    && mkdir -p /app/data \
    && chown -R fenrir:fenrir /app

USER fenrir

CMD ["python", "run.py"]
```

- [ ] **Step 4: Build the image and confirm the user**

Run:
```bash
cd /srv/project/python/FenrirBot && docker build -t fenrirbot:audit-test .
docker run --rm --entrypoint sh fenrirbot:audit-test -c 'id; pip show pytest 2>&1 | head -1'
```
Expected: `uid=10001(fenrir) gid=10001(fenrir)` and `WARNING: Package(s) not found: pytest`

- [ ] **Step 5: Point CI at the dev requirements**

In `.github/workflows/ci.yml`, replace the two lines in the `test` job:

```yaml
          cache-dependency-path: requirements.txt
      - run: pip install -r requirements.txt
```

with:

```yaml
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile requirements.txt requirements-dev.txt .github/workflows/ci.yml
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "build: run as uid 10001 and keep pytest out of the runtime image

The container ran as root with an empty CapDrop while holding the Discord
token and a socket-proxy route. Test deps move to requirements-dev.txt,
which CI now installs."
```

---

### Task 9: Make the three doc files describe the bot that exists

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: the command list as it stands after Task 7.
- Produces: no code changes; nothing else depends on this task.

**The command list, verified live on 2026-09-01 (14 synced):** `/up`, `/maintenance`, `/scheduled`, `/scheduled-list`, `/scheduled-cancel`, `/status`, `/ping`, `/containers`, `/stacks`, `/refresh`, `/dashboard`, `/rapport`, `/alerts`, `/server-config` (group: `validate`, `diff`, `apply`, `export`, `webhooks reveal`). Prefix commands: `!status` only.

- [ ] **Step 1: Rewrite the README's Features and Usage sections**

In `README.md`, replace the `## Features` block (`:5-12`) with:

```markdown
## Features

All commands are **administrator-only** except `/ping`.

**Announcements**
- **`/maintenance`** — announce a maintenance (update, backup, config, security patch, migration) with an interactive "terminé" button and an incident thread
- **`/up`** — announce a service is back
- **`/scheduled`** — schedule a future maintenance; it fires automatically (times are read as **Europe/Paris**)
- **`/scheduled-list`** / **`/scheduled-cancel`** — manage pending schedules
- **`/status`**, **`!status`** — quick status update

**Homelab readouts**
- **`/containers`**, **`/stacks`**, **`/refresh`** — Docker inventory via `socket-proxy`
- **`/dashboard`** — container status overview
- **`/rapport`** — CPU/RAM/network report from VictoriaMetrics
- **`/alerts`** — active Grafana alerts
- **`/ping`** — latency check (open to everyone)

**Server configuration**
- **`/server-config validate|diff|apply|export`** and **`/server-config webhooks reveal`** — declarative guild reconciliation from `specs/server-spec.yaml`. See [`src/server_config/README.md`](src/server_config/README.md).
```

- [ ] **Step 2: Fix the setup instructions**

Replace the `### 2. Quick Setup (Recommended)` and `### 3. Run the Bot` sections (`:50-79`) with:

```markdown
### 2. Setup

```bash
cd /srv/project/python/FenrirBot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Then edit `.env` with your values:
```
DISCORD_TOKEN=your_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678
```

> 💡 To get a channel ID: Enable Developer Mode in Discord settings, then right-click the channel → Copy ID

### 3. Run the Bot

```bash
source venv/bin/activate
python run.py
```

### 4. Run the tests

```bash
python3 -m pytest -q
```

### 5. Deploy

```bash
./build.sh                                        # builds fenrirbot:latest
cd /srv/nebula && ./scripts/start-docker.sh up management
```
```

- [ ] **Step 3: Delete the Netdata section and fix the Usage examples**

Delete the entire `## 🖥️ Netdata Integration (System Monitoring)` section (`:98-137` — everything from that heading up to `## Adding New Cogs`). Netdata was removed from this bot on 2026-04-17.

Replace the `## Usage Examples` block (`:82-97`) with:

```markdown
## Usage Examples

```
/maintenance service:traefik maintenance_type:security reason:Patch CVE duration:30 minutes
/up service:traefik
/scheduled service:plex when:2026-09-05 22:00 duration:1 heure reason:Migration DB
/status message:Tout est opérationnel
/rapport periode:weekly
/ping
```

> `when:` is read as **Europe/Paris** wall-clock time.
```

- [ ] **Step 4: Fix the cog list in the README's Project Structure**

In the `## Project Structure` block, replace the `cogs/` and `utils/` sub-trees with:

```
    ├── cogs/              # Command modules
    │   ├── downtime.py    # /maintenance, /up, /scheduled*
    │   ├── status.py      # /status, /ping
    │   ├── docker.py      # /containers, /stacks, /refresh
    │   ├── dashboard.py   # /dashboard
    │   ├── reports.py     # /rapport (VictoriaMetrics)
    │   ├── alerts.py      # /alerts (Grafana)
    │   └── server_config.py  # /server-config *
    ├── server_config/     # Declarative guild reconciliation
    └── utils/
        ├── embeds.py      # Embed builders
        ├── views.py       # Interactive buttons (persistent)
        ├── incidents.py   # Open-incident persistence
        ├── permissions.py # admin_only() gate
        ├── docker.py      # Docker SDK wrapper + cache
        ├── grafana.py     # Grafana REST client
        ├── victoriametrics.py
        ├── helpers.py     # Shared helpers, PARIS_TZ
        └── personality.py # Mood by time of day
```

Also delete the `scripts/` block from that same tree — there is no `scripts/` directory; the only script is `build.sh`.

- [ ] **Step 5: Fix CLAUDE.md**

In `CLAUDE.md`, replace the `## Commands` block (`:5-24`) with:

```markdown
## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

# Run the bot
python run.py

# Build and deploy
./build.sh
cd /srv/nebula && ./scripts/start-docker.sh up management
```

Run the tests with `python3 -m pytest -q` from the repo root.
CI runs them plus `ruff` on every pull request and on pushes to `dev`.
```

Replace the `### Cogs (`src/cogs/`)` list (`:39-44`) with:

```markdown
- **`downtime.py`** — Core cog. `/maintenance`, `/up`, `/scheduled`, `/scheduled-list`, `/scheduled-cancel`. Background `tasks.loop` checks every 30s for due scheduled maintenances. Times are parsed as **Europe/Paris** via `parse_local_datetime` and stored as UTC. Persists to `data/scheduled_maintenances.json`; open incidents to `data/open_incidents.json`.
- **`status.py`** — `/status`, `/ping`, `!status`.
- **`docker.py`** — `/containers`, `/stacks`, `/refresh`. Refreshes the container cache every 5 minutes off the event loop.
- **`dashboard.py`** — `/dashboard` (Docker status overview).
- **`reports.py`** — `/rapport`, VictoriaMetrics-backed.
- **`alerts.py`** — `/alerts`, Grafana Alertmanager-backed.
- **`server_config.py`** — `/server-config validate|diff|apply|export`, `webhooks reveal`. Declarative guild reconciliation from `specs/server-spec.yaml`.

**Permissions:** every command except `/ping` is gated by `admin_only()` from `src/utils/permissions.py`, which applies both `default_permissions` and a runtime `has_permissions` check.
```

Replace the `**`webhook_server.py`**` bullet in the Utils list with:

```markdown
- **`webhook_server.py`** — **Dead code.** The aiohttp server and its Traefik router were removed on 2026-08-30; `WEBHOOK_ENABLED` is not in the compose, so `src/bot.py` never constructs it. Kept only for reference.
- **`incidents.py`** — `IncidentStore`: persists open incident announcements so buttons survive a restart.
- **`permissions.py`** — `admin_only()` decorator.
```

Replace the `## Key `.env` variables` table rows for the webhook vars with a single note, and add the missing ones:

```markdown
| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required. Bot token. |
| `ANNOUNCEMENT_CHANNEL_ID` | Channel for downtime announcements. |
| `NOTIFICATION_ROLE_ID` | Role to `@mention` (falls back to `@here` if 0). |
| `VICTORIAMETRICS_URL` | VictoriaMetrics base URL (e.g. `http://victoriametrics:8428`). |
| `GRAFANA_URL` | Grafana base URL (e.g. `http://grafana:3000`). |
| `GRAFANA_API_KEY` | Grafana service account token (Viewer role). |
| `REPORTS_CHANNEL_ID` | **Dead config** — read by `Config` but no cog uses it. |

The `WEBHOOK_*` variables are not set in the deployed compose; the webhook server is dead code.
```

- [ ] **Step 6: Fix .env.example**

Replace `.env.example` entirely with:

```
# =============================================================
# FenrirBot — Environment Configuration
# Copy this file to .env and fill in your values
# =============================================================

# === Required ===
DISCORD_TOKEN=your_discord_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678

# === Optional ===
NOTIFICATION_ROLE_ID=0
COMMAND_PREFIX=!

# === VictoriaMetrics (/rapport) ===
VICTORIAMETRICS_URL=http://victoriametrics:8428

# === Grafana (/alerts) ===
GRAFANA_URL=http://grafana:3000
GRAFANA_API_KEY=

# === Dead config, kept because Config still reads it ===
REPORTS_CHANNEL_ID=0
```

- [ ] **Step 7: Verify no doc claims a command that does not exist**

Run:
```bash
grep -nE '/downtime|/backup|!down|!up|/netdata|scripts/setup\.sh|scripts/run\.sh|UPTIMEKUMA|NETDATA' README.md CLAUDE.md .env.example
```
Expected: no output (exit 1)

- [ ] **Step 8: Commit**

```bash
git add README.md CLAUDE.md .env.example
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "docs: describe the bot that exists

README advertised /downtime, /backup, !down, !up and three /netdata commands
— all deleted in the April 2026 merge and monitoring removal — plus a
scripts/ directory that does not exist. CLAUDE.md listed 4 cogs of 7 and
documented the removed webhook routes as live. .env.example carried seven
dead UPTIMEKUMA_* and two NETDATA_* vars and none of the three actually read."
```

---

### Task 10: Deploy and verify

**Files:**
- No source changes. Host and Discord verification only.

**Interfaces:**
- Consumes: everything from Tasks 1–9.
- Produces: `fenrirbot:latest` rebuilt and running as uid 10001, with the PR open against `dev`.

- [ ] **Step 1: Announce the maintenance in `#infra`**

```bash
docker exec slack-notifier curl -s -X POST localhost:8080/notify/infra \
  -H 'Content-Type: application/json' \
  -d '{"text":"🔧 FenrirBot: rebuild + recreate for the 2026-09-01 audit fixes (timezone, scheduler, permissions, non-root image). Expected downtime ~30s, Discord announcements only."}'
```

- [ ] **Step 2: Chown the data bind mount for the non-root image**

The container now runs as uid 10001 but `${DOCKERDIR}/appdata/fenrirbot/data` is root-owned. **This needs sudo — ask the user to run it if the agent has none:**

```bash
sudo chown -R 10001:10001 /srv/nebula/docker/appdata/fenrirbot/data
```

Verify: `ls -ln /srv/nebula/docker/appdata/fenrirbot/` → the `data` directory shows `10001 10001`.

- [ ] **Step 3: Build and deploy**

```bash
cd /srv/project/python/FenrirBot && ./build.sh
cd /srv/nebula && ./scripts/start-docker.sh recreate management
```

> Never use plain `docker compose` — only `start-docker.sh` injects the Infisical secrets.

- [ ] **Step 4: Verify the container**

```bash
docker exec fenrirbot id
docker logs fenrirbot --tail 30
```
Expected: `uid=10001(fenrir)`; logs show 7 cogs loaded, 14 slash commands synced, `Fenrir is online!`, and **no** `Docker refresh failed`.

- [ ] **Step 5: Verify the fixes in Discord**

- `/ping` as a non-admin → works.
- `/containers` as a non-admin → `⛔ Cette commande est réservée aux administrateurs.`
- `/scheduled service:test when:<two minutes from now, Paris time> duration:1 minute reason:audit verification` → the embed's `<t:...:F>` field must show the time you typed, and it must fire ~2 minutes later, not in 2 hours.
- `/scheduled-cancel service:test` if you would rather not wait.
- `/alerts` → real alert list (or "Aucune alerte"); temporarily breaking `GRAFANA_URL` should produce "Statut inconnu", not the green all-clear.
- Restart the container, then click the button on the still-open `/maintenance` announcement → it must work rather than "This interaction failed".

- [ ] **Step 6: Push and open the PR**

```bash
cd /srv/project/python/FenrirBot
git push -u origin fix/audit-2026-09-01
gh pr create --base dev --head fix/audit-2026-09-01 \
  --title "fix: 2026-09-01 audit remediation" \
  --body "$(cat <<'EOF'
Fixes every finding from the 2026-09-01 audit.

**Correctness**
- `/scheduled` read times as UTC while the container runs `TZ=Europe/Paris` — every schedule fired 2h late in summer
- A bare `assert` in the scheduler's `tasks.loop` ended the loop on a cache miss, silencing all future maintenances
- A deleted target channel caused the maintenance to be dropped without being announced
- Docker reads were `sparse=False` (1+90 inspects), blocking the event loop from autocomplete, and aborted entirely on a container-removal race (observed live)
- Incident buttons died on every restart — views are now persistent, backed by `data/open_incidents.json`
- `/alerts` rendered the green all-clear when Grafana was unreachable or the token was rejected
- `/server-config apply` could wipe a category's permission overwrites via `edit(overwrites={})`, reported as "unchanged"; `diff` now reports channel edits instead of always saying 0

**Security**
- Every command except `/ping` is administrator-only, enforced at runtime rather than only as a UI default
- Image runs as uid 10001; `pytest` moved to `requirements-dev.txt`

**Docs**
- README, CLAUDE.md and .env.example rewritten to describe the 14 commands that actually exist

Tests: 13 → 48.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: Close out in `#infra`**

```bash
docker exec slack-notifier curl -s -X POST localhost:8080/notify/infra \
  -H 'Content-Type: application/json' \
  -d '{"text":"✅ FenrirBot: audit fixes deployed and verified. Running as uid 10001, 14 commands synced, all but /ping now admin-only."}'
```

- [ ] **Step 8: Update the vault**

Delete the seven FenrirBot debt items and the two FenrirBot security items from `2_Projects/_Atlas/Open Threads.md`, add the outcome to `2_Projects/FenrirBot/FenrirBot.md`'s `## Decisions log`, and re-derive the counts by parsing the page rather than adjusting them. Keep the `REPORTS_CHANNEL_ID`, `/dashboard`, test-coverage and SQLite items — this plan does not close those. The `socket-proxy` security item stays too: it is filed under Nebula and is not fixed here.

---

## Self-Review

**Spec coverage** — each audit finding maps to a task: `/scheduled` timezone → 1; scheduler assert + silent drop → 2; docker N+1/blocking/race → 3; non-persistent views + 3s deadline → 4; `/alerts` false all-clear → 5; category overwrite wipe + dishonest diff → 6; permission guards → 7; root + pytest → 8; README/CLAUDE.md/.env.example → 9; deploy + vault → 10.

**Deliberately not covered** (left in Open Threads, and Task 10 Step 8 says to keep them): `REPORTS_CHANNEL_ID` dead config, the `/dashboard` decision, `data/*.json` → SQLite, the estate-wide `socket-proxy` write/exec grants, `_find_existing_first_message`'s 50-message limit, stale reaction bindings, `_handle_reaction` re-reading state per event, unique-role-*name* validation, and exporter slug collisions. None blocks the ten tasks above.

**Type consistency** — `parse_local_datetime`/`format_paris` (Task 1) are used only in Task 1's cog edit. `_trigger_scheduled_downtime` gains `-> bool` in Task 2 and is called in Task 2 and extended in Task 4; both use the same name. `ContainerInfo.stack` (Task 3) is read by `get_stacks` in the same task. `IncidentRecord`/`IncidentStore` (Task 4) are consumed by `views.py`, `downtime.py` and `bot.py` within Task 4. `admin_only()` (Task 7) is imported by seven cog files in that task. `get_active_alerts` returns `list | None` in Task 5 and the cog handles `None` in the same task.

**Ordering note** — Task 4 edits `_trigger_scheduled_downtime`, which Task 2 modifies. Run them in order. Tasks 5, 6, 8 and 9 are independent of everything else and can run in any order.
