"""Server performance reports via VictoriaMetrics"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional

from ..config import config
from ..utils.victoriametrics import VictoriaMetricsClient
from ..utils.helpers import create_progress_bar


_PERIODS = {
    "daily": {
        "label": "24 dernières heures",
        "delta": timedelta(hours=24),
        "step": "1h",
        "seconds": 86400,
    },
    "weekly": {
        "label": "7 derniers jours",
        "delta": timedelta(days=7),
        "step": "6h",
        "seconds": 604800,
    },
    "monthly": {
        "label": "30 derniers jours",
        "delta": timedelta(days=30),
        "step": "1d",
        "seconds": 2592000,
    },
}


def _fmt_bytes(b: Optional[float]) -> str:
    """Format a byte count as human-readable string."""
    if b is None:
        return "*N/A*"
    gb = b / 1_073_741_824
    if gb >= 1:
        return f"**{gb:.2f} GB**"
    mb = b / 1_048_576
    if mb >= 1:
        return f"**{mb:.1f} MB**"
    return f"**{b / 1024:.1f} KB**"


class ReportsCog(commands.Cog, name="Reports"):
    """Performance reports from VictoriaMetrics"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.vm = VictoriaMetricsClient(config.victoriametrics_url) if config and config.victoriametrics_url else None

    @app_commands.command(name="rapport", description="📊 Afficher un rapport de performance du serveur")
    @app_commands.describe(periode="Période du rapport (défaut: quotidien)")
    @app_commands.choices(periode=[
        app_commands.Choice(name="Quotidien (24h)", value="daily"),
        app_commands.Choice(name="Hebdomadaire (7j)", value="weekly"),
        app_commands.Choice(name="Mensuel (30j)", value="monthly"),
    ])
    async def rapport_slash(self, interaction: discord.Interaction, periode: str = "daily"):
        if not self.vm:
            await interaction.response.send_message(
                "❌ VictoriaMetrics non configuré (`VICTORIAMETRICS_URL` manquant).",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        period = _PERIODS[periode]
        now = datetime.now()
        start = now - period["delta"]
        step = period["step"]
        secs = period["seconds"]

        # CPU average and peak over period
        cpu_stats = await self.vm.query_range_stats(
            '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100',
            start, now, step,
        )

        # RAM usage % average and peak
        ram_stats = await self.vm.query_range_stats(
            "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
            start, now, step,
        )

        # Total network bytes transferred over the full period (instant queries)
        net_rx = await self.vm.query_instant(
            f'sum(increase(node_network_receive_bytes_total{{device!="lo"}}[{secs}s]))'
        )
        net_tx = await self.vm.query_instant(
            f'sum(increase(node_network_transmit_bytes_total{{device!="lo"}}[{secs}s]))'
        )

        embed = discord.Embed(
            title=f"📊 Rapport serveur — {period['label']}",
            color=0x5865F2,
            timestamp=now,
        )

        if cpu_stats:
            bar = create_progress_bar(cpu_stats["avg"], "cpu")
            embed.add_field(
                name="🖥️ CPU",
                value=f"Moy: {bar}\nPic: **{cpu_stats['max']:.1f}%**",
                inline=True,
            )
        else:
            embed.add_field(name="🖥️ CPU", value="*Indisponible*", inline=True)

        if ram_stats:
            bar = create_progress_bar(ram_stats["avg"], "ram")
            embed.add_field(
                name="🧠 RAM",
                value=f"Moy: {bar}\nPic: **{ram_stats['max']:.1f}%**",
                inline=True,
            )
        else:
            embed.add_field(name="🧠 RAM", value="*Indisponible*", inline=True)

        embed.add_field(
            name="🌐 Réseau",
            value=f"↓ Reçu: {_fmt_bytes(net_rx)}\n↑ Envoyé: {_fmt_bytes(net_tx)}",
            inline=True,
        )

        embed.set_footer(text="🐺 Fenrir • Données VictoriaMetrics")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(ReportsCog(bot))
