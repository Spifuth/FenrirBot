"""Netdata monitoring cog - System alerts and status from Netdata"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import aiohttp
import asyncio

from ..config import config
from ..utils.helpers import (
    create_progress_bar,
    is_netdata_configured,
    create_error_embed,
    THRESHOLDS
)


class NetdataStatus:
    """Status information from Netdata API"""
    def __init__(self, data: dict):
        self.hostname = data.get("hostname", "Unknown")
        self.os = data.get("os_name", "Unknown")
        self.os_version = data.get("os_version", "")
        self.kernel = data.get("kernel_name", "")
        self.architecture = data.get("architecture", "")
        self.cores = self._to_int(data.get("cores_total", 0))
        self.memory_total = self._to_int(data.get("ram_total", 0))  # in bytes
        self.uptime = self._to_float(data.get("uptime", 0))
    
    @staticmethod
    def _to_int(value) -> int:
        """Convert value to int, handling string representations"""
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0
    
    @staticmethod
    def _to_float(value) -> float:
        """Convert value to float, handling string representations"""
        try:
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0
        
    @property
    def memory_total_gb(self) -> float:
        """Get total memory in GB"""
        return self.memory_total / (1024 ** 3) if self.memory_total else 0
    
    @property
    def uptime_str(self) -> str:
        """Get uptime as a readable string"""
        seconds = int(self.uptime)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0 or not parts:
            parts.append(f"{minutes}m")
        
        return " ".join(parts)


class NetdataAlarm:
    """Alarm information from Netdata"""
    def __init__(self, data: dict):
        self.id = data.get("id", 0)
        self.name = data.get("name", "Unknown")
        self.chart = data.get("chart", "")
        self.family = data.get("family", "")
        self.status = data.get("status", "UNDEFINED")
        self.value = data.get("value", 0)
        self.units = data.get("units", "")
        self.info = data.get("info", "")
        self.last_status_change = data.get("last_status_change", 0)
        
    @property
    def status_emoji(self) -> str:
        """Get emoji for status"""
        return {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "CLEAR": "✅",
            "UNDEFINED": "❓",
        }.get(self.status, "❓")
    
    @property
    def status_color(self) -> int:
        """Get color for status"""
        return {
            "CRITICAL": 0xFF0000,
            "WARNING": 0xFFAA00,
            "CLEAR": 0x44FF44,
            "UNDEFINED": 0x808080,
        }.get(self.status, 0x808080)
    
    @property
    def display_name(self) -> str:
        """Get a readable name"""
        return self.name.replace("_", " ").replace(".", " → ").title()


class NetdataCog(commands.Cog):
    """Commands for Netdata system monitoring integration"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.netdata_url = getattr(config, 'netdata_url', '') if config else ''
        self.netdata_api_key = getattr(config, 'netdata_api_key', '') if config else ''
    
    def _get_headers(self) -> dict:
        """Get headers for Netdata API requests"""
        headers = {"Accept": "application/json"}
        if self.netdata_api_key:
            headers["Authorization"] = f"Bearer {self.netdata_api_key}"
        return headers
    
    async def _fetch_data(self, endpoint: str) -> Optional[dict]:
        """Fetch data from Netdata API"""
        if not self.netdata_url:
            return None
        
        url = f"{self.netdata_url.rstrip('/')}/api/v1/{endpoint}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, 
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        print(f"Netdata API error: {response.status}")
                        return None
        except asyncio.TimeoutError:
            print("Netdata API timeout")
            return None
        except Exception as e:
            print(f"Netdata API error: {e}")
            return None
    
    async def _fetch_metric(self, chart: str, after: int = -60, points: int = 1) -> Optional[dict]:
        """Fetch a specific metric chart"""
        endpoint = f"data?chart={chart}&after={after}&points={points}&format=json"
        return await self._fetch_data(endpoint)
    
    # ═══════════════════════════════════════════════════════════════
    # Slash Commands
    # ═══════════════════════════════════════════════════════════════
    
    netdata_group = app_commands.Group(
        name="netdata",
        description="🖥️ Commandes de monitoring système Netdata"
    )
    
    @netdata_group.command(name="status", description="📊 Afficher l'état actuel du système")
    async def netdata_status(self, interaction: discord.Interaction):
        """Show current system status from Netdata"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            embed = discord.Embed(
                title="❌ Netdata Non Configuré",
                description="L'URL de Netdata n'est pas configurée.\n\nAjoute `NETDATA_URL` dans ton fichier `.env`",
                color=0xFF4444
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Fetch system info
        info_data = await self._fetch_data("info")
        if not info_data:
            embed = discord.Embed(
                title="❌ Erreur de Connexion",
                description=f"Impossible de se connecter à Netdata:\n`{self.netdata_url}`",
                color=0xFF4444
            )
            await interaction.followup.send(embed=embed)
            return
        
        status = NetdataStatus(info_data)
        
        # Fetch current metrics
        cpu_data = await self._fetch_metric("system.cpu")
        ram_data = await self._fetch_metric("system.ram")
        disk_data = await self._fetch_metric("disk_space._")
        
        embed = discord.Embed(
            title=f"🖥️ État Système - {status.hostname}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # System info
        os_info = f"{status.os} {status.os_version}"
        if status.kernel:
            os_info += f" ({status.kernel})"
        
        embed.add_field(
            name="💻 Système",
            value=f"**OS:** {os_info}\n**Arch:** {status.architecture}\n**Cores:** {status.cores}",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Uptime",
            value=f"`{status.uptime_str}`",
            inline=True
        )
        
        embed.add_field(
            name="🧠 RAM Totale",
            value=f"`{status.memory_total_gb:.1f} GB`",
            inline=True
        )
        
        # CPU Usage
        if cpu_data and "data" in cpu_data:
            try:
                # Sum all CPU categories except idle
                values = cpu_data["data"][0][1:]  # Skip timestamp
                labels = cpu_data.get("labels", [])
                
                # Find idle index and calculate usage
                idle_idx = labels.index("idle") if "idle" in labels else -1
                if idle_idx > 0:
                    cpu_usage = 100 - values[idle_idx - 1]  # -1 because we skipped timestamp
                else:
                    cpu_usage = sum(values)
                
                bar = create_progress_bar(cpu_usage, "cpu")
                embed.add_field(name="🖥️ CPU", value=bar, inline=False)
            except (IndexError, KeyError):
                pass
        
        # RAM Usage
        if ram_data and "data" in ram_data:
            try:
                values = ram_data["data"][0][1:]
                labels = ram_data.get("labels", [])
                
                # Calculate used percentage
                total = sum(abs(v) for v in values if v)
                free_idx = labels.index("free") if "free" in labels else -1
                cached_idx = labels.index("cached") if "cached" in labels else -1
                buffers_idx = labels.index("buffers") if "buffers" in labels else -1
                
                free = abs(values[free_idx - 1]) if free_idx > 0 else 0
                cached = abs(values[cached_idx - 1]) if cached_idx > 0 else 0
                buffers = abs(values[buffers_idx - 1]) if buffers_idx > 0 else 0
                
                # Available = free + cached + buffers
                available = free + cached + buffers
                used_pct = ((total - available) / total * 100) if total > 0 else 0
                
                bar = create_progress_bar(used_pct, "ram")
                embed.add_field(name="🧠 RAM", value=bar, inline=False)
            except (IndexError, KeyError, ZeroDivisionError):
                pass
        
        # Disk Usage
        if disk_data and "data" in disk_data:
            try:
                values = disk_data["data"][0][1:]
                labels = disk_data.get("labels", [])
                
                avail_idx = labels.index("avail") if "avail" in labels else -1
                used_idx = labels.index("used") if "used" in labels else -1
                
                if avail_idx > 0 and used_idx > 0:
                    avail = abs(values[avail_idx - 1])
                    used = abs(values[used_idx - 1])
                    total = avail + used
                    used_pct = (used / total * 100) if total > 0 else 0
                    
                    bar = create_progress_bar(used_pct, "disk")
                    embed.add_field(name="💾 Disque (/)", value=bar, inline=False)
            except (IndexError, KeyError, ZeroDivisionError):
                pass
        
        embed.set_footer(text="🐺 Fenrir • Netdata Monitor")
        
        await interaction.followup.send(embed=embed)
    
    @netdata_group.command(name="alarms", description="🚨 Afficher les alertes actives")
    async def netdata_alarms(self, interaction: discord.Interaction):
        """Show active alarms from Netdata"""
        await interaction.response.defer(thinking=True)
        
        if not self.netdata_url:
            embed = discord.Embed(
                title="❌ Netdata Non Configuré",
                description="L'URL de Netdata n'est pas configurée.\n\nAjoute `NETDATA_URL` dans ton fichier `.env`",
                color=0xFF4444
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Fetch alarms
        alarms_data = await self._fetch_data("alarms?all")
        
        if not alarms_data:
            embed = discord.Embed(
                title="❌ Erreur de Connexion",
                description=f"Impossible de se connecter à Netdata:\n`{self.netdata_url}`",
                color=0xFF4444
            )
            await interaction.followup.send(embed=embed)
            return
        
        alarms_dict = alarms_data.get("alarms", {})
        
        # Parse and sort alarms
        alarms = []
        for alarm_data in alarms_dict.values():
            alarm = NetdataAlarm(alarm_data)
            if alarm.status in ["CRITICAL", "WARNING"]:
                alarms.append(alarm)
        
        # Sort by severity (CRITICAL first)
        alarms.sort(key=lambda a: (0 if a.status == "CRITICAL" else 1, a.name))
        
        if not alarms:
            embed = discord.Embed(
                title="✅ Aucune Alerte Active",
                description="Tous les systèmes fonctionnent normalement !",
                color=0x44FF44,
                timestamp=datetime.now()
            )
            embed.set_footer(text="🐺 Fenrir • Netdata Monitor")
            await interaction.followup.send(embed=embed)
            return
        
        # Count by severity
        critical_count = sum(1 for a in alarms if a.status == "CRITICAL")
        warning_count = sum(1 for a in alarms if a.status == "WARNING")
        
        # Determine embed color based on most severe alarm
        if critical_count > 0:
            color = 0xFF0000
            emoji = "🚨"
        else:
            color = 0xFFAA00
            emoji = "⚠️"
        
        embed = discord.Embed(
            title=f"{emoji} Alertes Actives ({len(alarms)})",
            description=f"🚨 **Critiques:** {critical_count}  |  ⚠️ **Avertissements:** {warning_count}",
            color=color,
            timestamp=datetime.now()
        )
        
        # Add alarms (max 10 to avoid embed limits)
        for alarm in alarms[:10]:
            value_str = f"{alarm.value}{alarm.units}" if alarm.units else str(alarm.value)
            
            field_value = f"**Valeur:** `{value_str}`"
            if alarm.chart:
                field_value += f"\n**Chart:** `{alarm.chart}`"
            if alarm.info:
                field_value += f"\n📋 {alarm.info[:100]}"
            
            embed.add_field(
                name=f"{alarm.status_emoji} {alarm.display_name}",
                value=field_value,
                inline=False
            )
        
        if len(alarms) > 10:
            embed.add_field(
                name="...",
                value=f"*Et {len(alarms) - 10} autres alertes*",
                inline=False
            )
        
        embed.set_footer(text="🐺 Fenrir • Netdata Monitor")
        
        await interaction.followup.send(embed=embed)
    
    @netdata_group.command(name="test", description="🧪 Envoyer une alerte de test")
    @app_commands.checks.has_permissions(administrator=True)
    async def netdata_test(self, interaction: discord.Interaction):
        """Send a test alert to verify webhook is working"""
        # Check if webhook server is configured
        if not self.bot.webhook_server:
            embed = discord.Embed(
                title="❌ Webhook Non Activé",
                description="Le serveur webhook n'est pas activé.\n\nActive `WEBHOOK_ENABLED=true` dans ton `.env`",
                color=0xFF4444
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Send test alert through the webhook handler
        await self.bot.webhook_server._send_alert(
            title="🧪 [TEST] Alert de Test Netdata",
            description=(
                "**CLEAR** → **WARNING**\n\n"
                "⚠️ **CPU**\n"
                "🟨🟨🟨🟨🟨🟨🟨🟨⬜⬜ **78.5%**\n\n"
                "📋 Ceci est une alerte de test pour vérifier l'intégration Netdata."
            ),
            color=0xFFAA00,
            fields=[
                {"name": "🖥️ Host", "value": "`test-server`", "inline": True},
                {"name": "📈 Chart", "value": "`system.cpu`", "inline": True},
            ],
            source="Netdata (Test)"
        )
        
        embed = discord.Embed(
            title="✅ Alerte de Test Envoyée",
            description="Vérifie le canal d'annonces pour voir l'alerte de test.",
            color=0x44FF44
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @netdata_test.error
    async def netdata_test_error(self, interaction: discord.Interaction, error):
        """Handle permission errors for test command"""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Tu as besoin des permissions d'administrateur pour cette commande.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    await bot.add_cog(NetdataCog(bot))
    print("  ✅ Loaded: Netdata monitoring cog")
