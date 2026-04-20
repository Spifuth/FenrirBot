"""Server performance reports via VictoriaMetrics"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional

from ..config import config
from ..utils.victoriametrics import VictoriaMetricsClient


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


def _bar(value: float, width: int = 10) -> str:
    """Render a fixed-width ASCII progress bar using █ and ·."""
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


def _fmt_bytes(b: Optional[float]) -> str:
    """Format byte count as a fixed-width right-aligned string for code blocks."""
    if b is None:
        return f"{'N/A':>10s}"
    gb = b / 1_073_741_824
    if gb >= 1:
        return f"{gb:>8.2f} GB"
    mb = b / 1_048_576
    if mb >= 1:
        return f"{mb:>8.1f} MB"
    return f"{b / 1024:>8.1f} KB"


def _stat_field(stats: Optional[dict]) -> str:
    """Render avg/pic bar lines in a code block, or n/a if unavailable."""
    if stats is None:
        return "```\nn/a\n```"
    return (
        f"```\n"
        f"avg  {_bar(stats['avg'])}  {stats['avg']:5.1f}%\n"
        f"pic  {_bar(stats['max'])}  {stats['max']:5.1f}%\n"
        f"```"
    )


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
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        period = _PERIODS[periode]
        now = datetime.now()
        start = now - period["delta"]
        secs = period["seconds"]

        cpu_stats = await self.vm.query_range_stats(
            '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100',
            start, now, period["step"],
        )
        ram_stats = await self.vm.query_range_stats(
            "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
            start, now, period["step"],
        )
        net_rx = await self.vm.query_instant(
            f'sum(increase(node_network_receive_bytes_total{{device!="lo"}}[{secs}s]))'
        )
        net_tx = await self.vm.query_instant(
            f'sum(increase(node_network_transmit_bytes_total{{device!="lo"}}[{secs}s]))'
        )

        embed = discord.Embed(
            title=f"Rapport · {period['label']}",
            color=0x2C2F33,
            timestamp=now,
        )
        embed.add_field(name="CPU", value=_stat_field(cpu_stats), inline=False)
        embed.add_field(name="RAM", value=_stat_field(ram_stats), inline=False)
        embed.add_field(
            name="Réseau",
            value=f"```\n↓  {_fmt_bytes(net_rx)}\n↑  {_fmt_bytes(net_tx)}\n```",
            inline=False,
        )
        embed.set_footer(text="Fenrir · VictoriaMetrics")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(ReportsCog(bot))
