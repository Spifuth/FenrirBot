"""Status and utility commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..utils.embeds import DowntimeEmbed
from ..utils.helpers import get_announcement_channel, get_notification_mention
from ..utils import uptimekuma as uptimekuma_module
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

    @app_commands.command(name="monitors", description="📊 Afficher l'état des sondes Uptime Kuma")
    @app_commands.describe(
        filter="Filtrer par statut (défaut: tous)"
    )
    @app_commands.choices(filter=[
        app_commands.Choice(name="🟢 En ligne uniquement", value="up"),
        app_commands.Choice(name="🔴 Hors ligne uniquement", value="down"),
        app_commands.Choice(name="⏸️ En pause uniquement", value="paused"),
        app_commands.Choice(name="📋 Tous", value="all"),
    ])
    async def monitors_slash(self, interaction: discord.Interaction, filter: str = "all"):
        """Display Uptime Kuma monitors status grouped by category"""
        await interaction.response.defer(ephemeral=True)
        
        if not uptimekuma_module.uptimekuma_auth_client:
            await interaction.followup.send(
                "❌ Uptime Kuma n'est pas configuré. Ajoutez les credentials dans `.env`",
                ephemeral=True
            )
            return
        
        try:
            await uptimekuma_module.uptimekuma_auth_client.connect()
            data = await uptimekuma_module.uptimekuma_auth_client.get_monitors_with_status()
            
            groups = data.get("groups", {})
            ungrouped = data.get("ungrouped", [])
            
            if not groups and not ungrouped:
                await interaction.followup.send("❌ Aucun monitor trouvé", ephemeral=True)
                return
            
            # Count totals
            all_monitors = [m for monitors in groups.values() for m in monitors] + ungrouped
            total = len(all_monitors)
            up_count = sum(1 for m in all_monitors if m.get('active') and m.get('status') == 1)
            down_count = sum(1 for m in all_monitors if m.get('active') and m.get('status') != 1)
            paused_count = sum(1 for m in all_monitors if not m.get('active'))
            
            # Build embed
            embed = discord.Embed(
                title="📊 Uptime Kuma - Sondes",
                description=(
                    f"**{total}** sonde(s) • "
                    f"🟢 {up_count} en ligne • "
                    f"🔴 {down_count} hors ligne • "
                    f"⏸️ {paused_count} en pause"
                ),
                color=0x5CDD8B if down_count == 0 else 0xFF4444,
                timestamp=datetime.now()
            )
            
            def format_monitor(m: dict) -> str:
                """Format a single monitor line"""
                mid = m.get('id', 0)
                name = m.get('name', 'Unknown')
                active = m.get('active', True)
                status = m.get('status', -1)
                mtype = m.get('type', 'HTTP')
                
                if not active:
                    emoji = "⏸️"
                elif status == 1:
                    emoji = "🟢"
                elif status == 0:
                    emoji = "🔴"
                else:
                    emoji = "🟡"
                
                return f"{emoji} `{mid:>2}` **{name}** ({mtype})"
            
            def should_show(m: dict) -> bool:
                """Check if monitor matches filter"""
                if filter == "all":
                    return True
                elif filter == "up":
                    return m.get('active') and m.get('status') == 1
                elif filter == "down":
                    return m.get('active') and m.get('status') != 1
                elif filter == "paused":
                    return not m.get('active')
                return True
            
            # Add groups as fields
            for group_name, monitors in sorted(groups.items()):
                filtered_monitors = [m for m in monitors if should_show(m)]
                if not filtered_monitors:
                    continue
                
                lines = [format_monitor(m) for m in filtered_monitors[:8]]
                if len(filtered_monitors) > 8:
                    lines.append(f"*+{len(filtered_monitors) - 8} autres...*")
                
                embed.add_field(
                    name=f"📁 {group_name} ({len(filtered_monitors)})",
                    value="\n".join(lines),
                    inline=False
                )
            
            # Add ungrouped monitors
            if ungrouped:
                filtered_ungrouped = [m for m in ungrouped if should_show(m)]
                if filtered_ungrouped:
                    lines = [format_monitor(m) for m in filtered_ungrouped[:8]]
                    if len(filtered_ungrouped) > 8:
                        lines.append(f"*+{len(filtered_ungrouped) - 8} autres...*")
                    
                    embed.add_field(
                        name=f"📄 Sans groupe ({len(filtered_ungrouped)})",
                        value="\n".join(lines),
                        inline=False
                    )
            
            embed.set_footer(text=f"Uptime Kuma • {config.uptimekuma_url if config else 'N/A'}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

    @app_commands.command(name="monitor", description="🔍 Voir les détails d'un monitor Uptime Kuma")
    @app_commands.describe(
        monitor_id="ID du monitor (visible avec /monitors)"
    )
    async def monitor_detail_slash(self, interaction: discord.Interaction, monitor_id: int):
        """Display detailed info for a specific monitor"""
        await interaction.response.defer(ephemeral=True)
        
        if not uptimekuma_module.uptimekuma_auth_client:
            await interaction.followup.send(
                "❌ Uptime Kuma n'est pas configuré",
                ephemeral=True
            )
            return
        
        try:
            await uptimekuma_module.uptimekuma_auth_client.connect()
            monitor = await uptimekuma_module.uptimekuma_auth_client.get_monitor_status(monitor_id)
            
            if not monitor:
                await interaction.followup.send(f"❌ Monitor ID {monitor_id} non trouvé", ephemeral=True)
                return
            
            # Status
            is_active = monitor.get("active", True)
            status = monitor.get("status", 0)
            
            if not is_active:
                status_text = "⏸️ En pause"
                color = 0x95A5A6
            elif status == 1:
                status_text = "🟢 En ligne"
                color = 0x5CDD8B
            elif status == 0:
                status_text = "🔴 Hors ligne"
                color = 0xFF4444
            else:
                status_text = "🟡 Pending"
                color = 0xFFAA00
            
            embed = discord.Embed(
                title=f"🔍 {monitor.get('name', 'Unknown')}",
                description=status_text,
                color=color,
                timestamp=datetime.now()
            )
            
            embed.add_field(name="ID", value=f"`{monitor_id}`", inline=True)
            embed.add_field(name="Type", value=monitor.get("type", "http"), inline=True)
            embed.add_field(name="Interval", value=f"{monitor.get('interval', 60)}s", inline=True)
            
            if monitor.get("url"):
                embed.add_field(name="URL", value=monitor.get("url"), inline=False)
            
            if monitor.get("hostname"):
                embed.add_field(name="Host", value=f"{monitor.get('hostname')}:{monitor.get('port', '')}", inline=False)
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

    @app_commands.command(name="pause", description="⏸️ Mettre en pause un monitor Uptime Kuma")
    @app_commands.describe(
        monitor_id="ID du monitor à mettre en pause"
    )
    async def pause_monitor_slash(self, interaction: discord.Interaction, monitor_id: int):
        """Pause a specific monitor"""
        if not uptimekuma_module.uptimekuma_auth_client:
            await interaction.response.send_message("❌ Uptime Kuma n'est pas configuré", ephemeral=True)
            return
        
        try:
            await uptimekuma_module.uptimekuma_auth_client.connect()
            success = await uptimekuma_module.uptimekuma_auth_client.pause_monitor(monitor_id)
            
            if success:
                await interaction.response.send_message(f"⏸️ Monitor ID `{monitor_id}` mis en pause", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Échec de la pause du monitor {monitor_id}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    @app_commands.command(name="resume", description="▶️ Reprendre un monitor Uptime Kuma")
    @app_commands.describe(
        monitor_id="ID du monitor à reprendre"
    )
    async def resume_monitor_slash(self, interaction: discord.Interaction, monitor_id: int):
        """Resume a paused monitor"""
        if not uptimekuma_module.uptimekuma_auth_client:
            await interaction.response.send_message("❌ Uptime Kuma n'est pas configuré", ephemeral=True)
            return
        
        try:
            await uptimekuma_module.uptimekuma_auth_client.connect()
            success = await uptimekuma_module.uptimekuma_auth_client.resume_monitor(monitor_id)
            
            if success:
                await interaction.response.send_message(f"▶️ Monitor ID `{monitor_id}` repris", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Échec de la reprise du monitor {monitor_id}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

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
