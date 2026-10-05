"""The REST sequence behind the incident buttons, and the reminder timer.

Button callbacks are driven through the item's bound callback
(`view.restore_button.callback(interaction)`), which is exactly what
discord.py's dispatcher calls on a click. Every view is built inside the
running loop and given a FakeIncidentStore, so nothing touches data/.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import discord

from src.utils.embeds import MaintenanceType
from src.utils.views import DowntimeView
from tests.discord_fakes import (
    FakeChannel,
    FakeIncidentStore,
    FakeInteraction,
    FakeMessage,
    FakeThread,
    FakeUser,
    field,
)

AUTHOR = 7


def _click(button_name, *, clicker=AUTHOR, revived=False, started_ago=timedelta(hours=2, minutes=5),
           duration="Inconnue", arm_timer=False):
    """Build a view, click one of its buttons, and return what happened."""
    store = FakeIncidentStore()
    inter = FakeInteraction(user=FakeUser(clicker, "Clicker"), channel_id=2)
    inter.message = FakeMessage(inter.log, message_id=4242, content="@here")

    async def scenario():
        view = DowntimeView(
            service="traefik",
            author_id=AUTHOR,
            duration_str=duration,
            announcement_channel=None if revived else FakeChannel(inter.log, channel_id=77),
            maintenance_type=MaintenanceType.DOWNTIME,
            store=store,
            started_at=datetime.now(timezone.utc) - started_ago,
        )
        if not revived:
            view.incident_thread = FakeThread(inter.log)
        if arm_timer:
            await view.start_timer()
        await getattr(view, button_name).callback(inter)
        await asyncio.sleep(0)  # let a cancelled timer task settle
        return view

    view = asyncio.run(scenario())
    return view, inter, store


# ── restore ────────────────────────────────────────────────────────────────

def test_restore_by_the_author_runs_the_full_close_sequence():
    view, inter, store = _click("restore_button")

    assert inter.log.names() == [
        "response.defer", "message.edit", "channel.send", "thread.send", "thread.edit", "followup.send",
    ]
    assert inter.log.of("response.defer")[0] == {"ephemeral": True}, \
        "must defer first: four REST calls follow and the deadline is 3 s"

    edited_view = inter.log.of("message.edit")[0]["view"]
    assert edited_view is view
    assert view.restore_button.disabled is True
    assert view.restore_button.label == "✅ Restored after 2h 5m"
    assert view.restore_button.style is discord.ButtonStyle.gray

    end = inter.log.of("channel.send")[0]
    assert end["channel"] == 77, "the end embed goes to the announcement channel"
    assert end["embed"].title == "Interruption terminée · traefik"
    assert field(end["embed"], "⏱️ Actual Downtime") == "2h 5m"

    assert "**Duration:** 2h 5m" in inter.log.of("thread.send")[0]["content"]
    assert inter.log.of("thread.edit")[0] == {"archived": True, "locked": True}
    assert store.removed == [4242]
    follow = inter.log.of("followup.send")[0]
    assert follow["content"] == "✅ **traefik** marked as restored!"
    assert follow["ephemeral"] is True
    assert view.resolved is True and view.is_finished()


def test_restore_on_a_revived_view_posts_in_the_clicked_channel_and_skips_the_thread():
    _, inter, store = _click("restore_button", revived=True, started_ago=timedelta(seconds=42))

    assert inter.log.names() == ["response.defer", "message.edit", "channel.send", "followup.send"]
    end = inter.log.of("channel.send")[0]
    assert end["channel"] == 2
    assert field(end["embed"], "⏱️ Actual Downtime") in {"42s", "43s"}
    assert store.removed == [4242]


def test_restore_by_someone_else_is_refused_and_changes_nothing():
    view, inter, store = _click("restore_button", clicker=999)

    assert inter.log.names() == ["response.send_message"]
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"].startswith("❌ Only the person who announced")
    assert reply["ephemeral"] is True
    assert store.removed == []
    assert view.resolved is False and not view.restore_button.disabled


def test_restore_cancels_the_pending_reminder():
    view, _, _ = _click("restore_button", duration="30 minutes", arm_timer=True)

    assert view.timer_task is not None
    assert view.timer_task.cancelled() or view.timer_task.done()


# ── cancel ─────────────────────────────────────────────────────────────────

def test_cancel_by_the_author_strikes_the_message_and_archives_the_thread():
    view, inter, store = _click("cancel_button")

    assert inter.log.names() == [
        "response.defer", "message.edit", "followup.send", "thread.send", "thread.edit",
    ]
    edit = inter.log.of("message.edit")[0]
    assert edit["content"] == "~~@here~~ **[CANCELLED]**"
    assert edit["view"] is view
    assert all(child.disabled for child in view.children)
    assert store.removed == [4242]
    assert inter.log.of("followup.send")[0]["content"] == \
        "🚫 Downtime announcement for **traefik** has been cancelled."
    assert inter.log.of("thread.edit")[0] == {"archived": True}
    assert view.resolved is True and view.is_finished()


def test_cancel_by_someone_else_is_refused_and_changes_nothing():
    view, inter, store = _click("cancel_button", clicker=999)

    assert inter.log.names() == ["response.send_message"]
    assert inter.log.of("response.send_message")[0]["ephemeral"] is True
    assert store.removed == []
    assert not any(child.disabled for child in view.children)


# ── reminder timer ─────────────────────────────────────────────────────────

def _run_timer(resolved_before_elapsed: bool):
    inter = FakeInteraction()

    async def scenario():
        view = DowntimeView(service="traefik", author_id=AUTHOR, duration_str="30 minutes",
                            store=FakeIncidentStore())
        view.duration = timedelta(microseconds=1)  # elapse at once (timedelta(0) is falsy: no timer)
        view.message = FakeMessage(inter.log)
        view.resolved = resolved_before_elapsed
        await view.start_timer()
        await view.timer_task

    asyncio.run(scenario())
    return inter.log


def test_reminder_replies_to_the_announcement_and_pings_the_author_once_elapsed():
    log = _run_timer(resolved_before_elapsed=False)

    [reply] = log.of("message.reply")
    assert "**traefik** (30 minutes) has elapsed" in reply["content"]
    assert f"<@{AUTHOR}>" in reply["content"]


def test_reminder_stays_silent_for_a_resolved_incident():
    assert _run_timer(resolved_before_elapsed=True).of("message.reply") == []


def test_unparseable_duration_never_arms_a_timer():
    async def scenario():
        view = DowntimeView(service="traefik", author_id=AUTHOR, duration_str="Inconnue",
                            store=FakeIncidentStore())
        await view.start_timer()
        return view

    assert asyncio.run(scenario()).timer_task is None
