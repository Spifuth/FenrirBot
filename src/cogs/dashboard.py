"""Dashboard and monitoring commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..config import config
from ..utils.docker import docker_manager
from ..utils.uptimekuma import uptimekuma_client, MonitorStatus
from ..utils.embeds import DashboardEmbed, progress_bar
from ..utils.helpers import (
    get_announcement_channel, 
    is_uptimekuma_configured,
    get_config_value,
    create_error_embed
)


class DashboardCog(commands.Cog, name="Dashboard"):
    """Commands for status dashboard and monitoring"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dashboard", description="📊 Afficher le tableau de bord des services")
    async def dashboard_slash(self, interaction: discord.Interaction):
        """Display a comprehensive status dashboard"""
        await interaction.response.defer()
        
        embeds = []
        
        # ========== Docker Containers Embed ==========
        containers = docker_manager.get_containers(include_stopped=True)
        
        if containers:
            running = [c for c in containers if c.state == "running"]
            stopped = [c for c in containers if c.state != "running"]
            
            docker_embed = DashboardEmbed.docker_status(containers, running, stopped)
            embeds.append(docker_embed)
        
        # ========== UptimeKuma Embed ==========
        if uptimekuma_client:
            try:
                monitors = await uptimekuma_client.get_monitors(
                    config.uptimekuma_status_page if config else "default"
                )
                
                if monitors:
                    up_monitors = [m for m in monitors if m.status == MonitorStatus.UP]
                    down_monitors = [m for m in monitors if m.status == MonitorStatus.DOWN]
                    
                    uk_embed = DashboardEmbed.uptimekuma_status(
                        monitors, 
                        len(up_monitors), 
                        len(down_monitors)
                    )
                    
                    # Add down services details if any
                    if down_monitors:
                        down_text = "\n".join([f"• **{m.name}**" for m in down_monitors[:8]])
                        uk_embed.add_field(
                            name="🚨 Services Down",
                            value=down_text,
                            inline=False
                        )
                    
                    embeds.append(uk_embed)
                    
            except Exception as e:
                error_embed = discord.Embed(
                    title="📊 UptimeKuma",
                    description=f"```\n⚠️ Connection Error\n```\n{str(e)[:100]}",
                    color=0xFFAA00
                )
                embeds.append(error_embed)
        
        # ========== No data ==========
        if not embeds:
            embeds.append(discord.Embed(
                title="📊 Dashboard",
                description="Aucune donnée de monitoring disponible.\n\n"
                           "• Les containers Docker apparaîtront quand Docker est accessible\n"
                           "• Configure `UPTIMEKUMA_URL` dans `.env` pour l'intégration UptimeKuma\n"
                           "• Configure `NETDATA_URL` pour le monitoring système",
                color=discord.Color.greyple()
            ))
        
        await interaction.followup.send(embeds=embeds)

    @app_commands.command(name="uptime", description="📡 Afficher le statut UptimeKuma d'un service")
    @app_commands.describe(service="Nom du service (laisser vide pour l'aperçu)")
    async def uptime_slash(self, interaction: discord.Interaction, service: str = None):
        """Show UptimeKuma uptime stats"""
        if not uptimekuma_client:
            await interaction.response.send_message(
                "❌ UptimeKuma non configuré. Configure `UPTIMEKUMA_URL` dans `.env`",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            monitors = await uptimekuma_client.get_monitors(
                config.uptimekuma_status_page if config else "default"
            )
            
            if service:
                # Find specific service
                monitor = next(
                    (m for m in monitors if service.lower() in m.name.lower()), 
                    None
                )
                
                if not monitor:
                    await interaction.followup.send(
                        f"❌ Aucun moniteur trouvé pour `{service}`",
                        ephemeral=True
                    )
                    return
                
                embed = discord.Embed(
                    title=f"{monitor.status.emoji} {monitor.name}",
                    color=discord.Color.green() if monitor.status == MonitorStatus.UP else discord.Color.red()
                )
                embed.add_field(name="Statut", value=monitor.status.label, inline=True)
                embed.add_field(name="Temps de réponse", value=f"{monitor.response_time}ms" if monitor.response_time else "N/A", inline=True)
                embed.add_field(name="Uptime (24h)", value=f"{monitor.uptime_24h:.2f}%" if monitor.uptime_24h else "N/A", inline=True)
                embed.add_field(name="Uptime (30j)", value=f"{monitor.uptime_30d:.2f}%" if monitor.uptime_30d else "N/A", inline=True)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # Vue d'ensemble
                up = sum(1 for m in monitors if m.status == MonitorStatus.UP)
                down = sum(1 for m in monitors if m.status == MonitorStatus.DOWN)
                total = len(monitors)
                
                embed = discord.Embed(
                    title="📊 Aperçu UptimeKuma",
                    color=discord.Color.green() if down == 0 else discord.Color.red()
                )
                embed.add_field(name="🟢 En ligne", value=str(up), inline=True)
                embed.add_field(name="🔴 Hors ligne", value=str(down), inline=True)
                embed.add_field(name="Total", value=str(total), inline=True)
                
                if down > 0:
                    down_list = [m.name for m in monitors if m.status == MonitorStatus.DOWN]
                    embed.add_field(
                        name="⚠️ Services hors ligne",
                        value="\n".join(f"• {name}" for name in down_list[:10]),
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erreur lors de la récupération des données UptimeKuma: `{str(e)[:100]}`",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DashboardCog(bot))
