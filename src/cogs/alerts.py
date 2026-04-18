"""Active Grafana alerts command"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from ..config import config
from ..utils.grafana import GrafanaClient
from ..utils.helpers import get_status_color, get_status_emoji


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
    except (ValueError, AttributeError):
        return ""


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
        """Display currently firing Grafana alerts"""
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
                title="🟢 Aucune alerte active",
                description="Tous les systèmes surveillés par Grafana fonctionnent normalement.",
                color=0x44FF44,
                timestamp=datetime.now(),
            )
            embed.set_footer(text="🐺 Fenrir • Grafana Alertmanager")
            await interaction.followup.send(embed=embed)
            return

        count = len(alerts)
        highest_severity = "warning"
        for alert in alerts:
            if alert.get("labels", {}).get("severity") == "critical":
                highest_severity = "critical"
                break

        embed = discord.Embed(
            title=f"🚨 {count} alerte(s) active(s)",
            color=get_status_color(highest_severity),
            timestamp=datetime.now(),
        )

        for alert in alerts[:10]:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            name = labels.get("alertname", "Alerte inconnue")
            severity = labels.get("severity", "warning")
            instance = labels.get("instance", labels.get("job", ""))
            summary = annotations.get("summary", annotations.get("description", ""))
            starts_at = alert.get("startsAt", "")

            emoji = get_status_emoji(severity)
            duration = _alert_duration(starts_at)

            lines = [f"{emoji} **{severity.upper()}**" + (f" — depuis {duration}" if duration else "")]
            if instance:
                lines.append(f"🖥️ `{instance}`")
            if summary:
                lines.append(summary[:120])

            embed.add_field(name=name, value="\n".join(lines), inline=False)

        overflow = count - 10
        footer = "🐺 Fenrir • Grafana Alertmanager"
        if overflow > 0:
            footer += f" • +{overflow} alerte(s) non affichée(s)"
        embed.set_footer(text=footer)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(AlertsCog(bot))
