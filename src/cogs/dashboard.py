"""Dashboard and monitoring commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..utils.docker import docker_manager
from ..utils.embeds import DashboardEmbed


class DashboardCog(commands.Cog, name="Dashboard"):
    """Commands for status dashboard and monitoring"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dashboard", description="📊 Afficher le tableau de bord des services")
    async def dashboard_slash(self, interaction: discord.Interaction):
        """Display a comprehensive status dashboard"""
        await interaction.response.defer()

        containers = docker_manager.get_containers(include_stopped=True)

        if not containers:
            await interaction.followup.send(embed=discord.Embed(
                title="📊 Dashboard",
                description=(
                    "Aucune donnée de monitoring disponible.\n\n"
                    "• Les containers Docker apparaîtront quand Docker est accessible"
                ),
                color=discord.Color.greyple()
            ))
            return

        running = [c for c in containers if c.state == "running"]
        stopped = [c for c in containers if c.state != "running"]
        docker_embed = DashboardEmbed.docker_status(containers, running, stopped)
        await interaction.followup.send(embed=docker_embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DashboardCog(bot))
