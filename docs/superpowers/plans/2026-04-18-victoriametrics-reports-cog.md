# VictoriaMetrics Reports Cog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the deleted `reports.py` cog with a `/rapport` slash command that fetches CPU, RAM, and network metrics from VictoriaMetrics and displays them in a Discord embed.

**Architecture:** A thin async HTTP wrapper (`src/utils/victoriametrics.py`) encapsulates all VictoriaMetrics API calls using the existing `aiohttp` dependency. The cog (`src/cogs/reports.py`) queries it per-request — no background polling. Three period choices: daily (24h), weekly (7d), monthly (30d). Stats are computed client-side from the query_range timeseries (avg, max). This project has no test suite; no tests are added.

**Tech Stack:** Python 3.11+, aiohttp (already a dep), VictoriaMetrics Prometheus-compatible API (`/api/v1/query`, `/api/v1/query_range`), discord.py 2.x

---

## Network context

FenrirBot and VictoriaMetrics both share the `t3_proxy` Docker network. FenrirBot can reach VictoriaMetrics at `http://victoriametrics:8428`. The `VICTORIAMETRICS_URL` env var is set to this value.

---

## File map

| Action | Path |
|--------|------|
| Create | `src/utils/victoriametrics.py` |
| Create | `src/cogs/reports.py` |
| Modify | `src/config.py` |
| Modify | `src/bot.py` |
| Modify | `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml` |

---

### Task 1: Add `victoriametrics_url` and `reports_channel_id` to config

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Add the two new fields to the `Config` dataclass**

Replace the existing `Config` dataclass body in `src/config.py` so it reads:

```python
@dataclass
class Config:
    """Bot configuration container"""
    token: str
    announcement_channel_id: int
    notification_role_id: int = 0
    command_prefix: str = "!"
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8085
    webhook_secret: str = ""
    victoriametrics_url: str = ""
    reports_channel_id: int = 0
```

- [ ] **Step 2: Add the env var loading for the two new fields in `from_env`**

The `return cls(...)` call inside `from_env` must include:

```python
        return cls(
            token=token,
            announcement_channel_id=int(channel_id),
            notification_role_id=int(role_id),
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
            webhook_enabled=os.getenv("WEBHOOK_ENABLED", "false").lower() == "true",
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=int(os.getenv("WEBHOOK_PORT", "8085")),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            victoriametrics_url=os.getenv("VICTORIAMETRICS_URL", ""),
            reports_channel_id=int(os.getenv("REPORTS_CHANNEL_ID", "0")),
        )
```

- [ ] **Step 3: Update CLAUDE.md env var table**

Add two rows to the Key `.env` variables table in `CLAUDE.md`:

```markdown
| `VICTORIAMETRICS_URL` | VictoriaMetrics base URL (e.g. `http://victoriametrics:8428`). |
| `REPORTS_CHANNEL_ID` | Channel for auto-posted reports (optional). |
```

- [ ] **Step 4: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/config.py CLAUDE.md
git commit -m "feat(config): add victoriametrics_url and reports_channel_id fields"
```

Expected: 2 files changed.

---

### Task 2: Create `src/utils/victoriametrics.py`

**Files:**
- Create: `src/utils/victoriametrics.py`

- [ ] **Step 1: Create the file**

```python
"""VictoriaMetrics HTTP client (Prometheus-compatible API)"""

import aiohttp
from datetime import datetime
from typing import Optional


class VictoriaMetricsClient:
    """Async HTTP client for VictoriaMetrics instant and range queries."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def query_instant(self, query: str) -> Optional[float]:
        """Run an instant query and return the first numeric value, or None on error."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/query"
            try:
                async with session.get(url, params={"query": query}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("data", {}).get("result", [])
                    if not results:
                        return None
                    return float(results[0]["value"][1])
            except Exception:
                return None

    async def query_range_stats(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str,
    ) -> Optional[dict]:
        """
        Run a range query and return {"avg": float, "max": float, "min": float}
        computed across all returned data points, or None on error/empty.
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/query_range"
            params = {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step,
            }
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("data", {}).get("result", [])
                    if not results:
                        return None

                    all_values: list[float] = []
                    for series in results:
                        for _ts, val in series.get("values", []):
                            try:
                                all_values.append(float(val))
                            except (ValueError, TypeError):
                                pass

                    if not all_values:
                        return None

                    return {
                        "avg": sum(all_values) / len(all_values),
                        "max": max(all_values),
                        "min": min(all_values),
                    }
            except Exception:
                return None
```

- [ ] **Step 2: Commit**

```bash
git add src/utils/victoriametrics.py
git commit -m "feat(utils): add VictoriaMetricsClient async HTTP wrapper"
```

---

### Task 3: Create `src/cogs/reports.py`

**Files:**
- Create: `src/cogs/reports.py`

- [ ] **Step 1: Create the file**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/cogs/reports.py
git commit -m "feat(cogs): add reports cog with /rapport command (VictoriaMetrics)"
```

---

### Task 4: Register the cog in `src/bot.py`

**Files:**
- Modify: `src/bot.py`

- [ ] **Step 1: Add the cog to INITIAL_COGS**

In `src/bot.py`, update `INITIAL_COGS` to include the new cog:

```python
    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
        "src.cogs.reports",
    ]
```

- [ ] **Step 2: Commit**

```bash
git add src/bot.py
git commit -m "feat(bot): register reports cog"
```

---

### Task 5: Add env vars to the nebula compose file and Infisical

**Files:**
- Modify: `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml`

- [ ] **Step 1: Add the two new env vars to `fenrirbot.yml`**

In the `environment:` block of `fenrirbot.yml`, add after `WEBHOOK_SECRET`:

```yaml
      VICTORIAMETRICS_URL: ${FENRIRBOT_VICTORIAMETRICS_URL}
      REPORTS_CHANNEL_ID: ${FENRIRBOT_REPORTS_CHANNEL_ID}
```

- [ ] **Step 2: Push secrets to Infisical**

```bash
source /srv/nebula/.infisical-auth
INFISICAL_TOKEN="$INFISICAL_ACCESS_TOKEN" infisical secrets set \
  FENRIRBOT_VICTORIAMETRICS_URL="http://victoriametrics:8428" \
  FENRIRBOT_REPORTS_CHANNEL_ID="0" \
  --projectId b13d9e15-c37e-462d-b695-5ebb96b7bda4 \
  --domain "$INFISICAL_DOMAIN" \
  --env prod
```

Set `FENRIRBOT_REPORTS_CHANNEL_ID` to `0` for now (means no auto-posting channel). Update it later with the real channel ID if you add scheduled auto-reports.

- [ ] **Step 3: Commit the compose file**

```bash
cd /srv/nebula
git add docker/services/management/fenrirbot/fenrirbot.yml
git commit -m "feat(fenrirbot): add VICTORIAMETRICS_URL and REPORTS_CHANNEL_ID env vars"
```

---

### Task 6: Build, deploy, and smoke-test

- [ ] **Step 1: Build the Docker image**

```bash
cd /srv/project/python/FenrirBot
./build.sh
```

Expected: `fenrirbot:latest` rebuilt successfully.

- [ ] **Step 2: Recreate the container**

```bash
cd /srv/nebula
./scripts/start-docker.sh recreate management
```

Expected: Infisical injects secrets, container starts, log shows `✅ Loaded: src.cogs.reports`.

- [ ] **Step 3: Check bot logs**

```bash
docker logs fenrirbot --tail 30
```

Expected output includes:
```
  ✅ Loaded: src.cogs.reports
  ✅ Synced N slash command(s)
```

- [ ] **Step 4: Test in Discord**

Run `/rapport periode:Quotidien` in Discord.

Expected: An embed appears with CPU%, RAM%, and network totals. If VictoriaMetrics has no data yet, fields will show `*Indisponible*` — that is correct behavior and not an error.

- [ ] **Step 5: Commit nebula git state**

```bash
cd /srv/nebula
git push
```

- [ ] **Step 6: Commit FenrirBot git state**

```bash
cd /srv/project/python/FenrirBot
git push
```
