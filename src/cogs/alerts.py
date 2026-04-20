"""Active Grafana alerts command"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from ..config import config
from ..utils.grafana import GrafanaClient


_SEV_WIDTH = 8  # len("CRITICAL") — all labels padded to this so · aligns


def _alert_duration(starts_at: str) -> str:
    """Return a human-readable duration string from an ISO 8601 timestamp."""
    try:
        start = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        total = int(delta.total_seconds())
        if total < 60:
            return f"{total}s"
        if total < 3600:
            return f"{total // 60}m"
        h = total // 3600
        m = (total % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    except ValueError:
        return ""


def _alert_field_value(severity: str, duration: str, instance: str, summary: str) -> str:
    """Build the code-block value for one alert field."""
    label = severity.upper().ljust(_SEV_WIDTH)
    line1 = label + (f" · depuis {duration}" if duration else "")
    lines = [line1]
    if instance:
        lines.append(instance)
    if summary:
        lines.append(summary[:100])
    return "```\n" + "\n".join(lines) + "\n```"


def _summary_description(alerts: list[dict]) -> str:
    """Build '1 critique · 2 avertissements' description line."""
    n_critical = sum(1 for a in alerts if a.get("labels", {}).get("severity") == "critical")
    n_warning = sum(1 for a in alerts if a.get("labels", {}).get("severity") == "warning")
    parts = []
    if n_critical:
        parts.append(f"{n_critical} critique{'s' if n_critical > 1 else ''}")
    if n_warning:
        parts.append(f"{n_warning} avertissement{'s' if n_warning > 1 else ''}")
    if not parts:
        n = len(alerts)
        parts.append(f"{n} alerte{'s' if n > 1 else ''}")
    return " · ".join(parts)


class AlertsCog(commands.Cog, name="Alerts"):
    """Grafana alert status commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.grafana = (
            GrafanaClient(config.grafana_url, config.grafana_api_key)
            if config and config.grafana_url and config.grafana_api_key
            else None
        )

    @app_commands.command(name="alerts", description="🚨 Afficher les alertes Grafana actives")
    async def alerts_slash(self, interaction: discord.Interaction):
        if not self.grafana:
            await interaction.response.send_message(
                "❌ Grafana non configuré (`GRAFANA_URL` ou `GRAFANA_API_KEY` manquant).",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        alerts = await self.grafana.get_active_alerts()

        if not alerts:
            embed = discord.Embed(
                title="Aucune alerte",
                description="Tous les systèmes sont opérationnels.",
                color=0x2C2F33,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="Fenrir · Grafana")
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Alertes · {len(alerts)}",
            description=_summary_description(alerts),
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        for alert in alerts[:10]:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            name = labels.get("alertname", "Alerte inconnue")
            severity = labels.get("severity", "warning")
            instance = labels.get("instance", labels.get("job", ""))
            summary = annotations.get("summary", annotations.get("description", ""))
            duration = _alert_duration(alert.get("startsAt", ""))
            embed.add_field(
                name=name,
                value=_alert_field_value(severity, duration, instance, summary),
                inline=False,
            )

        overflow = max(0, len(alerts) - 10)
        footer = "Fenrir · Grafana Alertmanager"
        if overflow > 0:
            footer += f" · +{overflow} non affichée(s)"
        embed.set_footer(text=footer)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(AlertsCog(bot))
