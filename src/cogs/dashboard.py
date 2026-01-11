"""Dashboard and monitoring commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..config import config
from ..utils.docker import docker_manager
from ..utils.uptimekuma import uptimekuma_client, MonitorStatus
from ..utils.embeds import DashboardEmbed, progress_bar


class DashboardCog(commands.Cog, name="Dashboard"):
    """Commands for status dashboard and monitoring"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _get_announcement_channel(self, fallback: discord.TextChannel) -> discord.TextChannel:
        """Get the configured announcement channel or fall back to current channel"""
        if config and config.announcement_channel_id:
            channel = self.bot.get_channel(config.announcement_channel_id)
            if channel:
                return channel
        return fallback

    @app_commands.command(name="dashboard", description="Show status dashboard of all services")
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
                description="No monitoring data available.\n\n"
                           "• Docker containers will appear when Docker is accessible\n"
                           "• Set `UPTIMEKUMA_URL` in `.env` for UptimeKuma integration",
                color=discord.Color.greyple()
            ))
        
        await interaction.followup.send(embeds=embeds)

    @app_commands.command(name="uptime", description="Show UptimeKuma status for a specific service")
    @app_commands.describe(service="Service name to check (leave empty for overview)")
    async def uptime_slash(self, interaction: discord.Interaction, service: str = None):
        """Show UptimeKuma uptime stats"""
        if not uptimekuma_client:
            await interaction.response.send_message(
                "❌ UptimeKuma not configured. Set `UPTIMEKUMA_URL` in `.env`",
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
                        f"❌ No monitor found matching `{service}`",
                        ephemeral=True
                    )
                    return
                
                embed = discord.Embed(
                    title=f"{monitor.status.emoji} {monitor.name}",
                    color=discord.Color.green() if monitor.status == MonitorStatus.UP else discord.Color.red()
                )
                embed.add_field(name="Status", value=monitor.status.label, inline=True)
                embed.add_field(name="Response Time", value=f"{monitor.response_time}ms" if monitor.response_time else "N/A", inline=True)
                embed.add_field(name="Uptime (24h)", value=f"{monitor.uptime_24h:.2f}%" if monitor.uptime_24h else "N/A", inline=True)
                embed.add_field(name="Uptime (30d)", value=f"{monitor.uptime_30d:.2f}%" if monitor.uptime_30d else "N/A", inline=True)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                # Overview
                up = sum(1 for m in monitors if m.status == MonitorStatus.UP)
                down = sum(1 for m in monitors if m.status == MonitorStatus.DOWN)
                total = len(monitors)
                
                embed = discord.Embed(
                    title="📊 UptimeKuma Overview",
                    color=discord.Color.green() if down == 0 else discord.Color.red()
                )
                embed.add_field(name="🟢 Up", value=str(up), inline=True)
                embed.add_field(name="🔴 Down", value=str(down), inline=True)
                embed.add_field(name="Total", value=str(total), inline=True)
                
                if down > 0:
                    down_list = [m.name for m in monitors if m.status == MonitorStatus.DOWN]
                    embed.add_field(
                        name="⚠️ Down Services",
                        value="\n".join(f"• {name}" for name in down_list[:10]),
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error fetching UptimeKuma data: `{str(e)[:100]}`",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DashboardCog(bot))
