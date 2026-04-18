# Grafana Alerts Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/alerts` slash command that queries Grafana's Alertmanager API and displays all currently firing alerts in a Discord embed, with per-alert severity, instance, summary, and firing duration.

**Architecture:** A thin async HTTP wrapper (`src/utils/grafana.py`) calls `GET /api/alertmanager/grafana/api/v2/alerts` with a Grafana service account token. The cog (`src/cogs/alerts.py`) calls it on demand and renders results in a single embed. If no alerts are firing, it shows a green "all clear" message. This project has no test suite; no tests are added.

**Tech Stack:** Python 3.11+, aiohttp (already a dep), Grafana REST API (service account token auth), discord.py 2.x

---

## Network context

FenrirBot and Grafana both share the `t3_proxy` Docker network. FenrirBot can reach Grafana at `http://grafana:3000`. The `GRAFANA_URL` env var is set to this value.

## Prerequisites

You need a Grafana **Service Account token** with Viewer role. Create it before Task 5:

1. In Grafana → **Administration → Service Accounts** → **"Add service account"**
2. Name: `fenrirbot-reader`, Role: `Viewer`
3. Click **"Add service account token"**, copy the token value
4. This becomes `FENRIRBOT_GRAFANA_API_KEY` in Infisical

---

## File map

| Action | Path |
|--------|------|
| Create | `src/utils/grafana.py` |
| Create | `src/cogs/alerts.py` |
| Modify | `src/config.py` |
| Modify | `src/bot.py` |
| Modify | `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml` |

---

### Task 1: Add `grafana_url` and `grafana_api_key` to config

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Add the two new fields to the `Config` dataclass**

The current dataclass ends at `webhook_secret`. If the VictoriaMetrics plan was applied first, it also has `victoriametrics_url` and `reports_channel_id`. Add after whichever is last:

```python
    grafana_url: str = ""
    grafana_api_key: str = ""
```

Full dataclass after both plans:

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
    grafana_url: str = ""
    grafana_api_key: str = ""
```

If the VictoriaMetrics plan was NOT applied, omit the `victoriametrics_url` and `reports_channel_id` lines.

- [ ] **Step 2: Add env var loading for the two new fields in `from_env`**

Inside the `return cls(...)` call, add at the end:

```python
            grafana_url=os.getenv("GRAFANA_URL", ""),
            grafana_api_key=os.getenv("GRAFANA_API_KEY", ""),
```

- [ ] **Step 3: Update CLAUDE.md env var table**

Add two rows to the Key `.env` variables table in `CLAUDE.md`:

```markdown
| `GRAFANA_URL` | Grafana base URL (e.g. `http://grafana:3000`). |
| `GRAFANA_API_KEY` | Grafana service account token (Viewer role). |
```

- [ ] **Step 4: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/config.py CLAUDE.md
git commit -m "feat(config): add grafana_url and grafana_api_key fields"
```

---

### Task 2: Create `src/utils/grafana.py`

**Files:**
- Create: `src/utils/grafana.py`

- [ ] **Step 1: Create the file**

```python
"""Grafana REST API client"""

import aiohttp
from datetime import datetime, timezone
from typing import Optional


class GrafanaClient:
    """Async HTTP client for the Grafana REST API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def get_active_alerts(self) -> list[dict]:
        """
        Fetch currently firing alerts from Grafana Alertmanager.

        Returns a list of alert dicts (Alertmanager v2 format), empty list on error.
        Each dict has keys: labels, annotations, startsAt, updatedAt, status, generatorURL
        """
        url = f"{self.base_url}/api/alertmanager/grafana/api/v2/alerts"
        params = {"active": "true", "silenced": "false", "inhibited": "false"}
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return []
                    return await resp.json()
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Returns True if Grafana API is reachable and authenticated."""
        url = f"{self.base_url}/api/health"
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False
```

- [ ] **Step 2: Commit**

```bash
git add src/utils/grafana.py
git commit -m "feat(utils): add GrafanaClient async HTTP wrapper"
```

---

### Task 3: Create `src/cogs/alerts.py`

**Files:**
- Create: `src/cogs/alerts.py`

- [ ] **Step 1: Create the file**

```python
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

        # More than 0 alerts — build the embed
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

        # Show up to 10 alerts as fields (Discord embed limit)
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
```

- [ ] **Step 2: Commit**

```bash
git add src/cogs/alerts.py
git commit -m "feat(cogs): add alerts cog with /alerts command (Grafana Alertmanager)"
```

---

### Task 4: Register the cog in `src/bot.py`

**Files:**
- Modify: `src/bot.py`

- [ ] **Step 1: Add the cog to INITIAL_COGS**

Update `INITIAL_COGS` (add `src.cogs.alerts` after any other cogs):

```python
    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
        "src.cogs.reports",   # present if VictoriaMetrics plan was applied
        "src.cogs.alerts",
    ]
```

If the VictoriaMetrics plan was not applied, omit `"src.cogs.reports"`.

- [ ] **Step 2: Commit**

```bash
git add src/bot.py
git commit -m "feat(bot): register alerts cog"
```

---

### Task 5: Create Grafana service account token (prerequisite)

- [ ] **Step 1: Create the service account in Grafana UI**

1. Open Grafana → **Administration → Service Accounts**
2. Click **"Add service account"**
3. Name: `fenrirbot-reader`, Role: `Viewer`
4. Click **"Create"**

- [ ] **Step 2: Generate a token**

1. Click **"Add service account token"**
2. Name: `fenrirbot`, expiry: No expiration (or set a long one)
3. Click **"Generate token"**
4. Copy the token — it is shown only once

---

### Task 6: Add env vars to the nebula compose file and Infisical

**Files:**
- Modify: `/srv/nebula/docker/services/management/fenrirbot/fenrirbot.yml`

- [ ] **Step 1: Add the two new env vars to `fenrirbot.yml`**

In the `environment:` block, add after `WEBHOOK_SECRET` (or after `REPORTS_CHANNEL_ID` if the VM plan was applied):

```yaml
      GRAFANA_URL: ${FENRIRBOT_GRAFANA_URL}
      GRAFANA_API_KEY: ${FENRIRBOT_GRAFANA_API_KEY}
```

- [ ] **Step 2: Push secrets to Infisical**

Replace `<token-from-task-5>` with the token you copied:

```bash
source /srv/nebula/.infisical-auth
INFISICAL_TOKEN="$INFISICAL_ACCESS_TOKEN" infisical secrets set \
  FENRIRBOT_GRAFANA_URL="http://grafana:3000" \
  FENRIRBOT_GRAFANA_API_KEY="<token-from-task-5>" \
  --projectId b13d9e15-c37e-462d-b695-5ebb96b7bda4 \
  --domain "$INFISICAL_DOMAIN" \
  --env prod
```

- [ ] **Step 3: Commit the compose file**

```bash
cd /srv/nebula
git add docker/services/management/fenrirbot/fenrirbot.yml
git commit -m "feat(fenrirbot): add GRAFANA_URL and GRAFANA_API_KEY env vars"
```

---

### Task 7: Build, deploy, and smoke-test

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

Expected: Infisical injects secrets, container starts.

- [ ] **Step 3: Check bot logs**

```bash
docker logs fenrirbot --tail 30
```

Expected output includes:
```
  ✅ Loaded: src.cogs.alerts
  ✅ Synced N slash command(s)
```

- [ ] **Step 4: Verify the Grafana connection**

```bash
docker exec fenrirbot python -c "
import asyncio, os
from src.utils.grafana import GrafanaClient
async def test():
    c = GrafanaClient(os.getenv('GRAFANA_URL'), os.getenv('GRAFANA_API_KEY'))
    ok = await c.health_check()
    print('Grafana reachable:', ok)
asyncio.run(test())
"
```

Expected: `Grafana reachable: True`

- [ ] **Step 5: Test in Discord**

Run `/alerts` in Discord.

- If no alerts are firing: green embed with "Aucune alerte active"
- If alerts are firing: red embed with per-alert fields showing severity, instance, and duration

- [ ] **Step 6: Push all changes**

```bash
cd /srv/project/python/FenrirBot
git push

cd /srv/nebula
git push
```
