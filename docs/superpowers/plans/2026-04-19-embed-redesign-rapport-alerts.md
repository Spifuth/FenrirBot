# Embed Redesign: /rapport and /alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the `/rapport` and `/alerts` Discord embeds to a Glances-style aesthetic — static dark colour, code-block fields, aligned ASCII bars using `█` and `·`.

**Architecture:** Two independent in-place rewrites. `src/cogs/reports.py` gets a `_bar()` helper and a reworked `_fmt_bytes()`, then uses them to build code-block fields. `src/cogs/alerts.py` gets `_alert_field_value()` and `_summary_description()` helpers and a fully reworked embed. No changes to any other file.

**Tech Stack:** Python 3.11+, discord.py 2.x. No new dependencies.

---

## File map

| Action | Path |
|--------|------|
| Rewrite | `src/cogs/reports.py` |
| Rewrite | `src/cogs/alerts.py` |

---

### Task 1: Rewrite `src/cogs/reports.py`

**Files:**
- Modify: `src/cogs/reports.py` (full rewrite)

No tests exist in this project — verify manually in Discord after deploy.

- [ ] **Step 1: Replace the file with the new implementation**

Write the following content to `src/cogs/reports.py` (working directory is the worktree or main repo root):

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/cogs/reports.py
git commit -m "redesign: /rapport embed — Glances-style code-block fields and ASCII bars"
```

Expected: 1 file changed.

---

### Task 2: Rewrite `src/cogs/alerts.py`

**Files:**
- Modify: `src/cogs/alerts.py` (full rewrite)

- [ ] **Step 1: Replace the file with the new implementation**

Write the following content to `src/cogs/alerts.py`:

```python
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
    except (ValueError, AttributeError):
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
        parts.append(f"{n_critical} critique")
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
                title="Aucune alerte",
                description="Tous les systèmes sont opérationnels.",
                color=0x2C2F33,
                timestamp=datetime.now(),
            )
            embed.set_footer(text="Fenrir · Grafana")
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Alertes · {len(alerts)}",
            description=_summary_description(alerts),
            color=0x2C2F33,
            timestamp=datetime.now(),
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

        overflow = len(alerts) - 10
        footer = "Fenrir · Grafana Alertmanager"
        if overflow > 0:
            footer += f" · +{overflow} non affichée(s)"
        embed.set_footer(text=footer)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(AlertsCog(bot))
```

- [ ] **Step 2: Commit**

```bash
git add src/cogs/alerts.py
git commit -m "redesign: /alerts embed — Glances-style code-block fields"
```

Expected: 1 file changed.

---

### Task 3: Build and deploy

- [ ] **Step 1: Build the image**

```bash
cd /srv/project/python/FenrirBot
./build.sh
```

Expected: `✓ fenrirbot:latest built`

- [ ] **Step 2: Redeploy**

```bash
cd /srv/nebula
./scripts/start-docker.sh recreate management
```

Expected: `Container fenrirbot Started`

- [ ] **Step 3: Verify in Discord**

Run `/rapport` — expect three code-block fields (CPU, RAM, Réseau) with `[█···]` bars, dark left border, footer `Fenrir · VictoriaMetrics`.

Run `/alerts` — expect either the "Aucune alerte" embed or an alert list with padded severity labels (`CRITICAL ·`, `WARNING  ·`).

- [ ] **Step 4: Commit plan file**

```bash
cd /srv/project/python/FenrirBot
git add docs/superpowers/plans/2026-04-19-embed-redesign-rapport-alerts.md
git commit -m "docs: add embed redesign implementation plan"
```
