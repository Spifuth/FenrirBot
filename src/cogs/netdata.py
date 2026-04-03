"""Netdata monitoring cog - System alerts and status from Netdata"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from typing import Optional
import aiohttp
import asyncio

from ..config import config


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
    
    # ═══════════════════════════════════════════════════════════════
    # Slash Commands
    # ═══════════════════════════════════════════════════════════════

    netdata_group = app_commands.Group(
        name="netdata",
        description="🖥️ Commandes de monitoring système Netdata"
    )

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


async def setup(bot: commands.Bot):
    """Setup function for loading the cog"""
    await bot.add_cog(NetdataCog(bot))
    print("  ✅ Loaded: Netdata monitoring cog")
