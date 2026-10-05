"""Discord-facing paths of the downtime cog: the five slash commands, the
service autocomplete, and the announcement a due scheduled maintenance posts.

The announce/queue decision of the 30 s loop is pinned separately in
test_downtime_scheduling.py; this file is about what reaches Discord. The cog
is built with __new__ (no tasks.loop), the incident store and docker_manager
are replaced with fakes, and persistence is a counter.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord

import src.cogs.downtime as downtime_module
from src.cogs.downtime import DowntimeCog, ScheduledMaintenance
from src.utils.embeds import MaintenanceType
from src.utils.helpers import parse_local_datetime
from src.utils.views import DowntimeView
from tests.discord_fakes import (
    FakeBot,
    FakeChannel,
    FakeIncidentStore,
    FakeInteraction,
    FakeMessage,
    FakeUser,
    field,
)


class FakeDocker:
    def __init__(self, containers=(), stacks=()):
        self.containers = list(containers)
        self.stacks = list(stacks)

    def get_container_names(self, include_stopped=True):
        return self.containers

    def get_stacks(self):
        return self.stacks


def make_cog(monkeypatch, bot=None, store=None, containers=("traefik", "grafana"),
             stacks=("core", "grafana"), queue=None):
    monkeypatch.setattr(downtime_module, "incident_store", store or FakeIncidentStore())
    monkeypatch.setattr(downtime_module, "docker_manager", FakeDocker(containers, stacks))
    cog = DowntimeCog.__new__(DowntimeCog)
    cog.bot = bot or FakeBot()
    cog._scheduled_maintenances = list(queue or [])
    cog._containers_cache = set()
    cog._stacks_cache = set()
    cog._unavailable_logged = set()
    cog.saves = 0

    def save():
        cog.saves += 1
    cog._save_scheduled_maintenances = save
    return cog


def scheduled(service="traefik", minutes_from_now=60.0, duration="Inconnue",
              maintenance_type="update", reason="test reason"):
    return ScheduledMaintenance(
        service=service,
        scheduled_time=datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now),
        duration=duration,
        reason=reason,
        author_id=1,
        channel_id=2,
        maintenance_type=maintenance_type,
    )


# ── /up ────────────────────────────────────────────────────────────────────

def test_up_announces_restoration_and_prunes_the_open_incident(monkeypatch):
    store = FakeIncidentStore()
    cog = make_cog(monkeypatch, store=store)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.up_slash.callback(cog, inter, service="traefik"))

    assert inter.log.names() == ["channel.send", "response.send_message"]
    sent = inter.log.of("channel.send")[0]
    assert sent["content"] is None, "mention defaults to off for /up"
    assert sent["embed"].title == "Service rétabli · traefik"
    assert sent["embed"].description == "Container opérationnel"
    assert store.removed_services == ["traefik"]
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "✅ Annonce de restauration envoyée pour **traefik** (Container)"
    assert reply["ephemeral"] is True


def test_up_with_mention_pings_and_types_an_unknown_service_as_other(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.up_slash.callback(cog, inter, service="nas", mention=True))

    sent = inter.log.of("channel.send")[0]
    assert sent["content"] == "@here"
    assert sent["embed"].description == "Service opérationnel"


def test_up_still_answers_when_the_incident_store_is_unwritable(monkeypatch):
    cog = make_cog(monkeypatch, store=FakeIncidentStore(raise_on={"remove_by_service"}))
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.up_slash.callback(cog, inter, service="traefik"))

    assert inter.log.names() == ["channel.send", "response.send_message"]


# ── /maintenance ───────────────────────────────────────────────────────────

def test_maintenance_posts_buttons_persists_the_incident_and_opens_a_thread(monkeypatch):
    store = FakeIncidentStore()
    cog = make_cog(monkeypatch, store=store)
    inter = FakeInteraction(user=FakeUser(7, "Spifuth"), channel_id=2)

    asyncio.run(DowntimeCog.maintenance_slash.callback(
        cog, inter, service="traefik", maintenance_type="security",
        reason="CVE-2026-0001", duration="30 minutes",
    ))

    assert inter.log.names() == [
        "channel.send", "message.create_thread", "thread.send", "response.send_message",
    ]
    sent = inter.log.of("channel.send")[0]
    assert sent["content"] == "@here", "mention defaults to on for /maintenance"
    embed = sent["embed"]
    assert embed.title == "Sécurité · traefik"
    assert field(embed, "Durée estimée") == "```\n30 minutes\n```"
    assert field(embed, "Détails") == "```\nCVE-2026-0001\n```"
    assert embed.footer.text == "Fenrir · Maintenance · Spifuth"

    view = sent["view"]
    assert isinstance(view, DowntimeView)
    assert view.author_id == 7
    assert view.maintenance_type is MaintenanceType.SECURITY
    assert view.restore_button.label == "✅ Patch appliqué"
    assert view.message is inter.channel.message
    assert view.incident_thread is inter.channel.message.thread

    [record] = store.added
    assert (record.message_id, record.channel_id, record.service, record.author_id) == (4242, 2, "traefik", 7)
    assert (record.duration_str, record.service_type, record.maintenance_type) == (
        "30 minutes", "container", "security",
    )
    assert datetime.now(timezone.utc) - datetime.fromisoformat(record.started_at) < timedelta(minutes=1)

    assert inter.log.of("message.create_thread")[0] == {
        "name": "◆ traefik - Sécurité", "auto_archive_duration": 1440,
    }
    reply = inter.log.of("response.send_message")[0]
    assert "<#9001>" in reply["content"]
    assert reply["ephemeral"] is True


def test_maintenance_without_mention_and_with_an_explicit_service_type(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.maintenance_slash.callback(
        cog, inter, service="traefik", maintenance_type="backup", reason="nightly",
        service_type="stack", mention=False,
    ))

    sent = inter.log.of("channel.send")[0]
    assert sent["content"] is None
    assert sent["embed"].description == "Stack en cours de sauvegarde"
    assert field(sent["embed"], "Durée estimée") == "```\nInconnue\n```"


def test_maintenance_still_posts_when_the_incident_store_is_unwritable(monkeypatch):
    cog = make_cog(monkeypatch, store=FakeIncidentStore(raise_on={"add"}))
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.maintenance_slash.callback(
        cog, inter, service="traefik", maintenance_type="update", reason="r",
    ))

    assert inter.log.names()[-1] == "response.send_message"


# ── /scheduled ─────────────────────────────────────────────────────────────

def test_scheduled_rejects_a_malformed_date_without_posting_or_queueing(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_slash.callback(
        cog, inter, service="traefik", when="demain 22h", duration="1h", reason="r",
    ))

    assert inter.log.names() == ["response.send_message"]
    assert inter.log.of("response.send_message")[0]["content"].startswith("❌ Format de date invalide")
    assert cog._scheduled_maintenances == [] and cog.saves == 0


def test_scheduled_rejects_a_past_date(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_slash.callback(
        cog, inter, service="traefik", when="2020-01-01 10:00", duration="1h", reason="r",
    ))

    assert inter.log.of("response.send_message")[0]["content"] == "❌ La date doit être dans le futur !"
    assert cog._scheduled_maintenances == [] and cog.saves == 0


def test_scheduled_announces_queues_and_saves_a_future_maintenance(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction(user=FakeUser(7, "Spifuth"))
    when = "2099-01-15 22:00"
    expected = parse_local_datetime(when)

    asyncio.run(DowntimeCog.scheduled_slash.callback(
        cog, inter, service="traefik", when=when, duration="2 heures",
        reason="Montée de version", maintenance_type="update",
    ))

    assert inter.log.names() == ["channel.send", "response.send_message"]
    sent = inter.log.of("channel.send")[0]
    assert sent["content"] == "@here"
    assert "view" not in sent, "the pre-announcement carries no buttons"
    embed = sent["embed"]
    assert embed.title == "Mise à jour planifié · traefik"
    assert field(embed, "⏰ Déclenchement auto").endswith(f"<t:{int(expected.timestamp())}:F>")

    [m] = cog._scheduled_maintenances
    # channel_id is deliberately not asserted: it stores the *invoking*
    # channel, while the pre-announcement goes to the announcement channel.
    # Whether the trigger should follow is an open question, not pinned here.
    assert (m.service, m.scheduled_time, m.duration, m.reason) == (
        "traefik", expected, "2 heures", "Montée de version",
    )
    assert (m.author_id, m.maintenance_type, m.announced) == (7, "update", False)
    assert cog.saves == 1
    reply = inter.log.of("response.send_message")[0]
    assert "1 maintenance(s) planifiée(s)" in reply["content"]
    assert reply["ephemeral"] is True


def test_scheduled_without_mention_posts_no_ping(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_slash.callback(
        cog, inter, service="traefik", when="2099-01-15 22:00", duration="1h",
        reason="r", mention=False,
    ))

    assert inter.log.of("channel.send")[0]["content"] is None


# ── /scheduled-list and /scheduled-cancel ──────────────────────────────────

def test_scheduled_list_when_empty(monkeypatch):
    cog = make_cog(monkeypatch)
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_list_slash.callback(cog, inter))

    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "📋 Aucune maintenance planifiée."
    assert reply["ephemeral"] is True


def test_scheduled_list_renders_one_field_per_entry(monkeypatch):
    a = scheduled("traefik", maintenance_type="update", duration="1h")
    b = scheduled("grafana", maintenance_type="bogus", reason="x" * 1000)
    cog = make_cog(monkeypatch, queue=[a, b])
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_list_slash.callback(cog, inter))

    reply = inter.log.of("response.send_message")[0]
    assert reply["ephemeral"] is True
    embed = reply["embed"]
    assert [f.name for f in embed.fields] == ["1. traefik", "2. grafana"]
    assert "Type : Mise à jour\nDurée: 1h" in embed.fields[0].value
    assert f"<t:{int(a.scheduled_time.timestamp())}:F>" in embed.fields[0].value
    assert "Type : Interruption" in embed.fields[1].value, "unknown type falls back to downtime"
    assert embed.fields[1].value.endswith("Raison : " + "x" * 900)


def test_scheduled_cancel_removes_the_matching_entry_case_insensitively(monkeypatch):
    keep = scheduled("grafana")
    cog = make_cog(monkeypatch, queue=[scheduled("Traefik"), keep])
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_cancel_slash.callback(cog, inter, service="traefik"))

    assert cog._scheduled_maintenances == [keep]
    assert cog.saves == 1
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"].startswith("✅ Maintenance planifiée pour **traefik** annulée.")
    assert reply["ephemeral"] is True


def test_scheduled_cancel_with_no_match_changes_nothing(monkeypatch):
    cog = make_cog(monkeypatch, queue=[scheduled("grafana")])
    inter = FakeInteraction()

    asyncio.run(DowntimeCog.scheduled_cancel_slash.callback(cog, inter, service="traefik"))

    assert len(cog._scheduled_maintenances) == 1 and cog.saves == 0
    assert inter.log.of("response.send_message")[0]["content"] == "❌ Aucune maintenance planifiée pour **traefik**"


# ── autocomplete ───────────────────────────────────────────────────────────

def test_service_autocomplete_lists_containers_then_stacks_without_duplicates(monkeypatch):
    cog = make_cog(monkeypatch, containers=("traefik", "grafana"), stacks=("core", "grafana"))

    choices = asyncio.run(cog.service_autocomplete(FakeInteraction(), ""))

    assert [(c.name, c.value) for c in choices] == [
        ("🐳 grafana", "grafana"), ("🐳 traefik", "traefik"), ("📚 core", "core"),
    ]


def test_service_autocomplete_filters_case_insensitively_and_caps_at_25(monkeypatch):
    cog = make_cog(monkeypatch, containers=[f"app-{i:02d}" for i in range(30)], stacks=["Media"])

    assert len(asyncio.run(cog.service_autocomplete(FakeInteraction(), ""))) == 25
    assert [c.value for c in asyncio.run(cog.service_autocomplete(FakeInteraction(), "APP-0"))] == [
        f"app-{i:02d}" for i in range(10)
    ]
    assert [c.value for c in asyncio.run(cog.service_autocomplete(FakeInteraction(), "mEDi"))] == ["Media"]


def test_container_and_stack_autocomplete_stay_in_their_lane(monkeypatch):
    cog = make_cog(monkeypatch, containers=("traefik",), stacks=("core",))

    assert [c.value for c in asyncio.run(cog.container_autocomplete(FakeInteraction(), ""))] == ["traefik"]
    assert [c.value for c in asyncio.run(cog.stack_autocomplete(FakeInteraction(), ""))] == ["core"]


# ── the announcement a due scheduled maintenance posts ─────────────────────

def _trigger_setup(monkeypatch, users=None, fetch_user_error=None, thread_error=None):
    store = FakeIncidentStore()
    inter = FakeInteraction()  # only used for its shared call log
    message = FakeMessage(inter.log)
    if thread_error is not None:
        async def broken(**kwargs):
            raise thread_error
        message.create_thread = broken
    channel = FakeChannel(inter.log, channel_id=2, message=message)
    bot = FakeBot(channels={2: channel}, users={1: FakeUser(1, "Spifuth")} if users is None else users,
                  fetch_user_error=fetch_user_error)
    cog = make_cog(monkeypatch, bot=bot, store=store)
    return cog, inter.log, store, message


def test_due_maintenance_posts_ping_buttons_thread_and_incident_record(monkeypatch):
    cog, log, store, message = _trigger_setup(monkeypatch)
    m = scheduled("traefik", minutes_from_now=-1, maintenance_type="migration")

    sent_ok = asyncio.run(cog._trigger_scheduled_downtime(m))

    assert sent_ok is True
    assert log.names() == ["channel.send", "message.create_thread", "thread.send"]
    sent = log.of("channel.send")[0]
    assert sent["content"] == "@here ⏰ **Maintenance planifiée démarrant maintenant!**"
    assert sent["embed"].title == "Migration · traefik"
    assert field(sent["embed"], "Détails") == "```\n[SCHEDULED] test reason\n```"
    assert sent["embed"].footer.text == "Fenrir · Maintenance · Spifuth"
    view = sent["view"]
    assert view.message is message and view.incident_thread is message.thread
    assert view.restore_button.label == "✅ Migration terminée"
    [record] = store.added
    assert (record.message_id, record.channel_id, record.maintenance_type) == (4242, 2, "migration")
    assert log.of("message.create_thread")[0]["name"] == "→ traefik - Migration"


def test_late_maintenance_says_so_in_the_ping_and_the_thread(monkeypatch):
    cog, log, _, _ = _trigger_setup(monkeypatch)
    m = scheduled("traefik", minutes_from_now=-30)

    asyncio.run(cog._trigger_scheduled_downtime(m, is_catchup=True))

    content = log.of("channel.send")[0]["content"]
    assert content == "@here ⚠️ **Maintenance planifiée (retard 30min - bot hors ligne)**"
    assert "triggered late because the bot was offline" in log.of("thread.send")[0]["content"]


def test_due_maintenance_with_a_parseable_duration_arms_the_reminder(monkeypatch):
    cog, log, _, _ = _trigger_setup(monkeypatch)
    m = scheduled("traefik", minutes_from_now=-1, duration="30 minutes")

    asyncio.run(cog._trigger_scheduled_downtime(m))

    assert log.of("channel.send")[0]["view"].timer_task is not None


def test_author_missing_from_cache_is_fetched(monkeypatch):
    cog, log, _, _ = _trigger_setup(monkeypatch, users={})

    asyncio.run(cog._trigger_scheduled_downtime(scheduled(minutes_from_now=-1)))

    assert cog.bot.fetched == [1]
    assert log.of("channel.send")[0]["embed"].footer.text == "Fenrir · Maintenance · fetched-1"


def test_author_who_left_renders_as_inconnu(monkeypatch):
    gone = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown User")
    cog, log, _, _ = _trigger_setup(monkeypatch, users={}, fetch_user_error=gone)

    assert asyncio.run(cog._trigger_scheduled_downtime(scheduled(minutes_from_now=-1))) is True
    assert log.of("channel.send")[0]["embed"].footer.text == "Fenrir · Maintenance · inconnu"


def test_thread_failure_after_the_ping_still_counts_as_sent(monkeypatch):
    # The role has already been pinged; returning False here would leave the
    # entry queued and the 30 s loop would re-ping on every tick.
    cog, log, store, _ = _trigger_setup(monkeypatch, thread_error=RuntimeError("no perms"))

    assert asyncio.run(cog._trigger_scheduled_downtime(scheduled(minutes_from_now=-1))) is True
    assert log.names() == ["channel.send"]
    assert len(store.added) == 1


def test_unresolvable_channel_is_not_sent_and_logged_once(monkeypatch, capsys):
    cog = make_cog(monkeypatch, bot=FakeBot(channels={}))
    m = scheduled(minutes_from_now=-1)

    first = asyncio.run(cog._trigger_scheduled_downtime(m))
    second = asyncio.run(cog._trigger_scheduled_downtime(m))

    assert (first, second) == (False, False)
    assert capsys.readouterr().out.count("unavailable") == 1
