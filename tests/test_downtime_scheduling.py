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
from src.utils.embeds import ServiceType


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


class _GotPastTheGuard(Exception):
    """Raised by the fake channel's send() to prove the guard let us through."""


class FakeVoiceLikeChannel(discord.abc.Messageable):
    """A Messageable that is NOT a TextChannel or Thread — i.e. text-in-voice."""

    async def _get_channel(self):  # required by the Messageable ABC
        return self

    async def send(self, *a, **kw):
        raise _GotPastTheGuard()


def test_a_messageable_that_is_not_a_textchannel_gets_past_the_channel_guard():
    # A TextChannel-only guard once made /scheduled run from a thread — and
    # still makes it run from a text-in-voice channel — permanently unable to
    # announce: the trigger returned False forever and the entry never fired.
    # Reaching send() is the proof we got past the guard.
    cog = make_cog([], FakeTrigger({}))
    cog.bot = FakeBot(channel=FakeVoiceLikeChannel(), author=FakeAuthor())
    cog._get_service_type = lambda _s: ServiceType.OTHER
    m = make_maintenance("svc", minutes_from_now=-1)

    try:
        asyncio.run(DowntimeCog._trigger_scheduled_downtime(cog, m))
    except _GotPastTheGuard:
        pass
    else:
        raise AssertionError(
            "the channel guard rejected a Messageable that is not a TextChannel; "
            "the entry would sit unannounced forever"
        )


def test_stale_entry_is_dropped_instead_of_queued_forever():
    ancient = make_maintenance("ancient", minutes_from_now=-60 * 24 * 8)  # 8 days overdue
    recent = make_maintenance("recent", minutes_from_now=-1)
    trigger = FakeTrigger({"recent": True})
    cog = make_cog([ancient, recent], trigger)

    run_check(cog)

    assert [m.service for m in cog._scheduled_maintenances] == []
    assert trigger.calls == ["recent"], "the stale entry must not be announced on its way out"


def test_entry_just_inside_the_stale_window_is_still_attempted():
    m = make_maintenance("svc", minutes_from_now=-60 * 24 * 6)  # 6 days overdue
    trigger = FakeTrigger({"svc": True})
    cog = make_cog([m], trigger)

    run_check(cog)

    assert trigger.calls == ["svc"]


def test_catchup_keeps_an_entry_whose_trigger_returns_false():
    m = make_maintenance("traefik", minutes_from_now=-10)
    cog = make_cog([m], FakeTrigger({"traefik": False}))

    asyncio.run(cog._catchup_missed_maintenances())

    assert [x.service for x in cog._scheduled_maintenances] == ["traefik"]
    assert cog._scheduled_maintenances[0].announced is False


def test_catchup_survives_a_raising_entry_and_still_announces_the_next():
    cog = make_cog(
        [make_maintenance("boom", minutes_from_now=-10),
         make_maintenance("traefik", minutes_from_now=-10)],
        FakeTrigger({"boom": KeyError("x"), "traefik": True}),
    )

    asyncio.run(cog._catchup_missed_maintenances())

    assert [x.service for x in cog._scheduled_maintenances] == ["boom"]


def test_catchup_removes_an_entry_it_announced():
    cog = make_cog([make_maintenance("traefik", minutes_from_now=-10)],
                   FakeTrigger({"traefik": True}))

    asyncio.run(cog._catchup_missed_maintenances())

    assert cog._scheduled_maintenances == []
