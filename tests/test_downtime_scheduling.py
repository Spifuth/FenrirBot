"""Pins the announce/queue decision made by DowntimeCog.check_scheduled_maintenances.

No Discord connection is made anywhere here: the cog is built with __new__
(skipping __init__, which would start the tasks.loop), and
_trigger_scheduled_downtime / _save_scheduled_maintenances are replaced with
plain fakes. The loop body is driven directly through the underlying
coroutine (Loop.coro), never through the tasks.loop scheduling machinery.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import discord

import src.cogs.downtime as downtime_module
from src.cogs.downtime import DowntimeCog, ScheduledMaintenance


def make_maintenance(
    service: str, minutes_from_now: float, announced: bool = False
) -> ScheduledMaintenance:
    return ScheduledMaintenance(
        service=service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
        duration="30 minutes",
        reason="test reason",
        author_id=1,
        channel_id=2,
        maintenance_type="downtime",
        announced=announced,
    )


class FakeTrigger:
    """Stub for _trigger_scheduled_downtime, keyed by maintenance.service.

    A result of True/False is returned; an Exception instance is raised
    instead of returned.
    """

    def __init__(self, results: dict):
        self.results = results
        self.calls: list[str] = []

    async def __call__(self, maintenance: ScheduledMaintenance, is_catchup: bool = False) -> bool:
        self.calls.append(maintenance.service)
        outcome = self.results[maintenance.service]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def make_cog(maintenances: list, trigger: FakeTrigger) -> DowntimeCog:
    """Build a DowntimeCog without running __init__ (no tasks.loop, no bot)."""
    cog = DowntimeCog.__new__(DowntimeCog)
    cog.bot = None
    cog._scheduled_maintenances = maintenances
    cog._containers_cache = set()
    cog._stacks_cache = set()
    cog._trigger_scheduled_downtime = trigger
    cog._save_scheduled_maintenances = lambda: None
    return cog


def run_check(cog: DowntimeCog) -> None:
    """Drive one tick of the loop body directly via the wrapped coroutine."""
    asyncio.run(DowntimeCog.check_scheduled_maintenances.coro(cog))


def test_trigger_true_removes_entry_from_queue():
    m = make_maintenance("svc-a", minutes_from_now=-1)
    cog = make_cog([m], FakeTrigger({"svc-a": True}))

    run_check(cog)

    assert cog._scheduled_maintenances == []


def test_trigger_false_keeps_entry_queued_and_unannounced():
    m = make_maintenance("svc-a", minutes_from_now=-1)
    cog = make_cog([m], FakeTrigger({"svc-a": False}))

    run_check(cog)

    assert cog._scheduled_maintenances == [m]
    assert m.announced is False


def test_trigger_raising_keeps_entry_queued_without_propagating():
    m = make_maintenance("svc-a", minutes_from_now=-1)
    cog = make_cog([m], FakeTrigger({"svc-a": RuntimeError("boom")}))

    # If the exception escaped the loop body, this call would raise and the
    # test would error out here -- completing normally is the assertion.
    run_check(cog)

    assert cog._scheduled_maintenances == [m]
    assert m.announced is False


def test_one_entry_raising_does_not_block_a_second_due_entry():
    bad = make_maintenance("svc-bad", minutes_from_now=-5)
    good = make_maintenance("svc-good", minutes_from_now=-1)
    trigger = FakeTrigger({"svc-bad": RuntimeError("boom"), "svc-good": True})
    cog = make_cog([bad, good], trigger)

    run_check(cog)

    assert cog._scheduled_maintenances == [bad]
    assert bad.announced is False
    assert good.announced is True
    assert set(trigger.calls) == {"svc-bad", "svc-good"}


def test_future_entry_is_not_triggered():
    future = make_maintenance("svc-future", minutes_from_now=10)
    trigger = FakeTrigger({})
    cog = make_cog([future], trigger)

    run_check(cog)

    assert cog._scheduled_maintenances == [future]
    assert future.announced is False
    assert trigger.calls == []


# ── Store-write-guard regression test ───────────────────────────────────────
#
# Unlike the tests above, this one exercises the *real* _trigger_scheduled_downtime
# (not FakeTrigger), so it needs enough plain fakes to satisfy the discord.py
# calls that method makes. Subclassing the real discord.py model classes
# (rather than duck-typing unrelated objects) keeps the isinstance(channel,
# (discord.TextChannel, discord.Thread)) check in _trigger_scheduled_downtime
# honest; __init__ is fully overridden so no network/state machinery runs.

class FakeAuthor:
    display_name = "Spifuth"


class FakeThread(discord.Thread):
    def __init__(self):
        self.id = 9001
        self.sent: list = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeMessage(discord.Message):
    def __init__(self, message_id: int, thread: FakeThread):
        self.id = message_id
        self.content = ""
        self._thread = thread

    async def create_thread(self, *args, **kwargs):
        return self._thread


class FakeChannel(discord.TextChannel):
    def __init__(self, channel_id: int, message: FakeMessage):
        self.id = channel_id
        self._message = message

    async def send(self, *args, **kwargs):
        return self._message


class FakeBot:
    """Stand-in for commands.Bot covering only what _trigger_scheduled_downtime calls."""

    def __init__(self, channel, author):
        self._channel = channel
        self._author = author

    def get_channel(self, channel_id):
        return self._channel

    def get_user(self, user_id):
        return self._author


class RaisingIncidentStore:
    """Stand-in for incident_store whose add() always fails, e.g. a
    read-only data/ mount."""

    def add(self, record):
        raise PermissionError("disk full simulation")


def make_real_cog(maintenances: list, bot) -> DowntimeCog:
    """Build a DowntimeCog without running __init__, keeping the real
    _trigger_scheduled_downtime (unlike make_cog, which fakes it out)."""
    cog = DowntimeCog.__new__(DowntimeCog)
    cog.bot = bot
    cog._scheduled_maintenances = maintenances
    cog._containers_cache = set()
    cog._stacks_cache = {"placeholder"}  # non-empty: skip the Docker-hitting cache refresh
    cog._save_scheduled_maintenances = lambda: None
    return cog


def test_incident_store_failure_does_not_block_announcement(monkeypatch):
    """incident_store.add() raising (e.g. PermissionError on a read-only
    mount) must not stop the announcement from being marked sent --
    otherwise check_scheduled_maintenances would treat the maintenance as
    unannounced and re-ping it every 30s forever."""
    monkeypatch.setattr(downtime_module, "incident_store", RaisingIncidentStore())

    thread = FakeThread()
    message = FakeMessage(message_id=42, thread=thread)
    channel = FakeChannel(channel_id=2, message=message)
    bot = FakeBot(channel=channel, author=FakeAuthor())

    m = make_maintenance("svc-a", minutes_from_now=-1)
    m.duration = "Inconnue"  # parse_duration -> None: no background timer task left dangling
    cog = make_real_cog([m], bot)

    run_check(cog)

    assert cog._scheduled_maintenances == []
    assert m.announced is True
