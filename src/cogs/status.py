"""Status and utility commands"""

import discord
from discord import app_commands
from discord.ext import commands

from ..config import config
from ..utils.embeds import DowntimeEmbed


class StatusCog(commands.Cog, name="Status"):
    """Commands for status updates and bot info"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _get_announcement_channel(self, fallback: discord.TextChannel) -> discord.TextChannel:
        """Get the configured announcement channel or fall back to current channel"""
        if config and config.announcement_channel_id:
            channel = self.bot.get_channel(config.announcement_channel_id)
            if channel:
                return channel
        return fallback

    @app_commands.command(name="status", description="Send a quick status update message")
    @app_commands.describe(message="Status message to send")
    async def status_slash(self, interaction: discord.Interaction, message: str):
        """Send a status update via slash command"""
        channel = self._get_announcement_channel(interaction.channel)
        embed = DowntimeEmbed.status(message, interaction.user)
        
        await channel.send(embed=embed)
        await interaction.response.send_message("✅ Status update sent", ephemeral=True)

    @app_commands.command(name="ping", description="Check if the bot is responsive")
    async def ping_slash(self, interaction: discord.Interaction):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latency: {latency}ms", ephemeral=True)

    @commands.command(name="status")
    async def status_prefix(self, ctx: commands.Context, *, message: str):
        """Quick status update: !status Everything is fine"""
        channel = self._get_announcement_channel(ctx.channel)
        embed = DowntimeEmbed.status(message, ctx.author)
        
        await channel.send(embed=embed)
        await ctx.message.add_reaction("✅")


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(StatusCog(bot))
