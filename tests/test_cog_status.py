"""Discord-facing paths of the status cog: /status, /ping and !status."""

import asyncio
from types import SimpleNamespace

from src.cogs.status import StatusCog
from src.utils import helpers
from tests.discord_fakes import FakeBot, FakeChannel, FakeContext, FakeInteraction


def _configure(monkeypatch, channel_id=0, role_id=0):
    monkeypatch.setattr(helpers, "config", SimpleNamespace(
        announcement_channel_id=channel_id, notification_role_id=role_id,
    ))


def test_status_posts_in_the_invoking_channel_when_no_announcement_channel_is_set():
    inter = FakeInteraction(channel_id=2)
    cog = StatusCog(FakeBot())

    asyncio.run(StatusCog.status_slash.callback(cog, inter, message="Tout va bien"))

    assert inter.log.names() == ["channel.send", "response.send_message"]
    sent = inter.log.of("channel.send")[0]
    assert sent["channel"] == 2
    assert sent["content"] is None, "mention defaults to off"
    assert sent["embed"].description == "Tout va bien"
    assert sent["embed"].footer.text == "Fenrir · Statut · Spifuth"
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "✅ Mise à jour envoyée"
    assert reply["ephemeral"] is True


def test_status_goes_to_the_announcement_channel_and_pings_the_role(monkeypatch):
    _configure(monkeypatch, channel_id=77, role_id=55)
    inter = FakeInteraction(channel_id=2)
    announce = FakeChannel(inter.log, channel_id=77)
    cog = StatusCog(FakeBot(channels={77: announce}))

    asyncio.run(StatusCog.status_slash.callback(cog, inter, message="Redémarrage", mention=True))

    sent = inter.log.of("channel.send")
    assert [s["channel"] for s in sent] == [77], "must not also post in the invoking channel"
    assert sent[0]["content"] == "<@&55>"


def test_status_falls_back_to_the_invoking_channel_when_the_configured_one_is_gone(monkeypatch):
    _configure(monkeypatch, channel_id=77)
    inter = FakeInteraction(channel_id=2)
    cog = StatusCog(FakeBot(channels={}))  # 77 does not resolve

    asyncio.run(StatusCog.status_slash.callback(cog, inter, message="x", mention=True))

    sent = inter.log.of("channel.send")[0]
    assert sent["channel"] == 2
    assert sent["content"] == "@here", "no role configured: mention falls back to @here"


def test_ping_reports_latency_in_milliseconds_ephemerally():
    inter = FakeInteraction()
    cog = StatusCog(FakeBot(latency=0.0423))

    asyncio.run(StatusCog.ping_slash.callback(cog, inter))

    assert inter.log.names() == ["response.send_message"]
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "🏓 Pong! Latence: 42ms"
    assert reply["ephemeral"] is True


def test_prefix_status_posts_the_embed_then_reacts():
    ctx = FakeContext()
    cog = StatusCog(FakeBot())

    asyncio.run(StatusCog.status_prefix.callback(cog, ctx, message="Tout roule"))

    assert ctx.log.names() == ["channel.send", "message.add_reaction"]
    assert ctx.log.of("channel.send")[0]["embed"].description == "Tout roule"
    assert ctx.log.of("message.add_reaction")[0]["emoji"] == "✅"
