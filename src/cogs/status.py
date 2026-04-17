"""Status and utility commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..utils.embeds import DowntimeEmbed
from ..utils.helpers import get_announcement_channel, get_notification_mention
from ..config import config


class StatusCog(commands.Cog, name="Status"):
    """Commands for status updates and bot info"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="status", description="Envoyer une mise à jour de statut")
    @app_commands.describe(
        message="Message de statut à envoyer",
        mention="Mentionner le rôle de notification (défaut: Non)"
    )
    async def status_slash(self, interaction: discord.Interaction, message: str, mention: bool = False):
        """Send a status update via slash command"""
        channel = get_announcement_channel(self.bot, interaction.channel)
        embed = DowntimeEmbed.status(message, interaction.user)
        assert channel is not None
        await channel.send(
            content=get_notification_mention() if mention else None,
            embed=embed
        )
        await interaction.response.send_message("✅ Mise à jour envoyée", ephemeral=True)

    @app_commands.command(name="ping", description="Vérifier si le bot répond")
    async def ping_slash(self, interaction: discord.Interaction):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latence: {latency}ms", ephemeral=True)

    @commands.command(name="status")
    async def status_prefix(self, ctx: commands.Context, *, message: str):
        """Quick status update: !status Everything is fine"""
        channel = get_announcement_channel(self.bot, ctx.channel)
        embed = DowntimeEmbed.status(message, ctx.author)
        assert channel is not None
        await channel.send(embed=embed)
        await ctx.message.add_reaction("✅")


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(StatusCog(bot))
