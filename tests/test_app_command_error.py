"""What a user sees when a slash command is denied or fails.

FenrirBot.on_app_command_error is the Discord-facing half of every cog's
admin gate. It never reads `self`, so it is called unbound with None rather
than constructing a Bot (which would need intents and a token).
"""

import asyncio

from discord import app_commands

from src.bot import FenrirBot
from tests.discord_fakes import FakeInteraction


def _handle(interaction, error):
    asyncio.run(FenrirBot.on_app_command_error(None, interaction, error))


def test_a_non_admin_gets_a_clear_ephemeral_refusal():
    inter = FakeInteraction()

    _handle(inter, app_commands.MissingPermissions(["administrator"]))

    assert inter.log.names() == ["response.send_message"]
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "⛔ Cette commande est réservée aux administrateurs."
    assert reply["ephemeral"] is True


def test_a_failure_before_any_response_answers_through_the_response():
    inter = FakeInteraction()

    _handle(inter, app_commands.AppCommandError("boom"))

    reply = inter.log.of("response.send_message")[0]
    assert reply["content"] == "❌ Une erreur est survenue lors de l'exécution de cette commande."
    assert reply["ephemeral"] is True


def test_a_failure_after_defer_answers_through_the_followup():
    inter = FakeInteraction()
    asyncio.run(inter.response.defer())

    _handle(inter, app_commands.AppCommandError("boom"))

    assert inter.log.names() == ["response.defer", "followup.send"]
    assert inter.log.of("followup.send")[0]["ephemeral"] is True
