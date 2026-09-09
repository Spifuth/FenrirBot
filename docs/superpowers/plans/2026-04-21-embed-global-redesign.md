# Global Embed Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the Glances-style aesthetic to every Discord embed in the bot — static dark colour `0x2C2F33`, no emojis in titles or footers, no GIFs or thumbnails, no personality text, code-block fields, ASCII bars, middle-dot `·` separators.

**Architecture:** Four independent in-place rewrites touching six files. `src/utils/embeds.py` is the biggest change (DowntimeEmbed × 5, DashboardEmbed × 1, remove EmbedAssets/FenrirPersonality). Three cog files get small embed-only updates. `src/utils/webhook_server.py` drops emoji colour logic and gets a local `_bar()`. `src/utils/helpers.py` gets uniform colour and no-emoji defaults. No new files, no new dependencies.

**Tech Stack:** Python 3.11+, discord.py 2.x. Worktree: `~/.config/superpowers/worktrees/FenrirBot/feature/embed-global-redesign`

---

## File map

| Action | Path |
|--------|------|
| Rewrite | `src/utils/embeds.py` |
| Modify | `src/cogs/downtime.py` |
| Modify | `src/cogs/docker.py` |
| Modify | `src/cogs/dashboard.py` |
| Rewrite | `src/utils/webhook_server.py` |
| Modify | `src/utils/helpers.py` |

---

### Task 1: Rewrite `src/utils/embeds.py`

**Files:**
- Rewrite: `src/utils/embeds.py`

No tests — verify manually after deploy.

- [ ] **Step 1: Replace the file**

Write the following to `src/utils/embeds.py`:

```python
"""Discord embed builders for announcements"""

import discord
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union


class ServiceType(Enum):
    """Type of service being announced"""
    CONTAINER = "container"
    STACK = "stack"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {
            ServiceType.CONTAINER: "Container",
            ServiceType.STACK: "Stack",
            ServiceType.OTHER: "Service",
        }.get(self, "Service")


class MaintenanceType(Enum):
    """Type of maintenance being performed"""
    DOWNTIME = "downtime"
    UPDATE = "update"
    BACKUP = "backup"
    CONFIG = "config"
    SECURITY = "security"
    MIGRATION = "migration"
    OTHER = "other"

    @property
    def icon(self) -> str:
        """Kept for backward compatibility with downtime cog scheduled-list."""
        return {
            MaintenanceType.DOWNTIME: "▼",
            MaintenanceType.UPDATE: "↑",
            MaintenanceType.BACKUP: "◼",
            MaintenanceType.CONFIG: "≡",
            MaintenanceType.SECURITY: "◆",
            MaintenanceType.MIGRATION: "→",
            MaintenanceType.OTHER: "·",
        }.get(self, "·")

    @property
    def label(self) -> str:
        return {
            MaintenanceType.DOWNTIME: "Interruption",
            MaintenanceType.UPDATE: "Mise à jour",
            MaintenanceType.BACKUP: "Sauvegarde",
            MaintenanceType.CONFIG: "Configuration",
            MaintenanceType.SECURITY: "Sécurité",
            MaintenanceType.MIGRATION: "Migration",
            MaintenanceType.OTHER: "Maintenance",
        }.get(self, "Maintenance")

    @property
    def verb(self) -> str:
        return {
            MaintenanceType.DOWNTIME: "hors ligne",
            MaintenanceType.UPDATE: "en cours de mise à jour",
            MaintenanceType.BACKUP: "en cours de sauvegarde",
            MaintenanceType.CONFIG: "en reconfiguration",
            MaintenanceType.SECURITY: "en cours de patching",
            MaintenanceType.MIGRATION: "en cours de migration",
            MaintenanceType.OTHER: "en maintenance",
        }.get(self, "en maintenance")


def _bar(value: float, width: int = 10) -> str:
    """Render a fixed-width ASCII progress bar using █ and ·."""
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


class DowntimeEmbed:
    """Helper class to create consistent downtime embeds"""

    @staticmethod
    def start(
        service: str,
        reason: str,
        estimated_duration: str,
        author: Union[discord.User, discord.Member],
        service_type: ServiceType = ServiceType.OTHER,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Interruption · {service}",
            description=f"{service_type.label} hors ligne",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Durée estimée", value=f"```\n{estimated_duration}\n```", inline=True)
        embed.add_field(name="Raison", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Downtime · {author.display_name}")
        return embed

    @staticmethod
    def maintenance(
        service: str,
        reason: str,
        estimated_duration: str,
        author: Union[discord.User, discord.Member],
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: Optional["MaintenanceType"] = None,
    ) -> discord.Embed:
        if maintenance_type is None:
            maintenance_type = MaintenanceType.OTHER
        embed = discord.Embed(
            title=f"{maintenance_type.label} · {service}",
            description=f"{service_type.label} {maintenance_type.verb}",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Type", value=f"```\n{maintenance_type.label}\n```", inline=True)
        embed.add_field(name="Durée estimée", value=f"```\n{estimated_duration}\n```", inline=True)
        embed.add_field(name="Détails", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Maintenance · {author.display_name}")
        return embed

    @staticmethod
    def end(
        service: str,
        author: Union[discord.User, discord.Member],
        service_type: ServiceType = ServiceType.OTHER,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Service rétabli · {service}",
            description=f"{service_type.label} opérationnel",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Statut", value="```\nOPERATIONNEL\n```", inline=True)
        embed.set_footer(text=f"Fenrir · Downtime · {author.display_name}")
        return embed

    @staticmethod
    def scheduled(
        service: str,
        scheduled_time: str,
        duration: str,
        reason: str,
        author: Union[discord.User, discord.Member],
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: Optional["MaintenanceType"] = None,
    ) -> discord.Embed:
        if maintenance_type is None:
            maintenance_type = MaintenanceType.DOWNTIME
        embed = discord.Embed(
            title=f"{maintenance_type.label} planifié · {service}",
            description=f"{service_type.label}",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Type", value=f"```\n{maintenance_type.label}\n```", inline=True)
        embed.add_field(name="Date", value=f"```\n{scheduled_time}\n```", inline=True)
        embed.add_field(name="Durée", value=f"```\n{duration}\n```", inline=True)
        embed.add_field(name="Détails", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Planifié · {author.display_name}")
        return embed

    @staticmethod
    def status(message: str, author: Union[discord.User, discord.Member]) -> discord.Embed:
        embed = discord.Embed(
            title="Mise à jour de statut",
            description=message,
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Fenrir · Statut · {author.display_name}")
        return embed


class DashboardEmbed:
    """Embed builders for dashboard displays"""

    @staticmethod
    def docker_status(containers: list, running: list, stopped: list) -> discord.Embed:
        total = len(containers)
        running_pct = (len(running) / total * 100) if total > 0 else 0

        embed = discord.Embed(
            title="Docker",
            description=f"```\n{_bar(running_pct)}  {len(running)}/{total} en cours\n```",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        if running:
            lines = []
            for c in running[:12]:
                suffix = ""
                if "healthy" in c.status.lower():
                    suffix = " ok"
                elif "unhealthy" in c.status.lower():
                    suffix = " err"
                lines.append(f"{c.display_name}{suffix}")
            if len(running) > 12:
                lines.append(f"+{len(running) - 12} autres")
            embed.add_field(
                name=f"En cours ({len(running)})",
                value="```\n" + "\n".join(lines) + "\n```",
                inline=True,
            )

        if stopped:
            lines = [c.display_name for c in stopped[:8]]
            if len(stopped) > 8:
                lines.append(f"+{len(stopped) - 8} autres")
            embed.add_field(
                name=f"Arrêtés ({len(stopped)})",
                value="```\n" + "\n".join(lines) + "\n```",
                inline=True,
            )

        embed.set_footer(text="Fenrir · Docker")
        return embed
```

- [ ] **Step 2: Commit**

```bash
git add src/utils/embeds.py
git commit -m "redesign: embeds.py — Glances-style, strip EmbedAssets/personality/GIFs"
```

Expected: 1 file changed.

---

### Task 2: Update three cog embeds

**Files:**
- Modify: `src/cogs/downtime.py` (scheduled-list embed only — lines ~636-657)
- Modify: `src/cogs/docker.py` (containers and stacks embeds)
- Modify: `src/cogs/dashboard.py` (fallback no-data embed)

- [ ] **Step 1: Update `scheduled_list_slash` in `src/cogs/downtime.py`**

Replace the embed block starting at line ~636 inside `scheduled_list_slash`. The old block:

```python
        embed = discord.Embed(
            title="📋 Maintenances Planifiées",
            color=0x3498DB
        )
        
        for i, m in enumerate(self._scheduled_maintenances, 1):
            # Get maintenance type info
            try:
                maint_type = MaintenanceType(m.maintenance_type)
            except ValueError:
                maint_type = MaintenanceType.DOWNTIME
            
            embed.add_field(
                name=f"{i}. {maint_type.icon} {m.service}",
                value=f"🏷️ Type: **{maint_type.label}**\n"
                      f"⏰ <t:{int(m.scheduled_time.timestamp())}:F>\n"
                      f"⏱️ Durée: {m.duration}\n"
                      f"📝 {m.reason}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
```

Replace with:

```python
        embed = discord.Embed(
            title="Maintenances planifiées",
            color=0x2C2F33,
        )

        for i, m in enumerate(self._scheduled_maintenances, 1):
            try:
                maint_type = MaintenanceType(m.maintenance_type)
            except ValueError:
                maint_type = MaintenanceType.DOWNTIME

            embed.add_field(
                name=f"{i}. {m.service}",
                value=(
                    f"```\n"
                    f"Type : {maint_type.label}\n"
                    f"Durée: {m.duration}\n"
                    f"```"
                    f"\nDéclenchement : <t:{int(m.scheduled_time.timestamp())}:F>"
                    f"\nRaison : {m.reason}"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
```

- [ ] **Step 2: Update `/containers` embed in `src/cogs/docker.py`**

Replace the embed block inside `containers_slash` (the old block from `embed = discord.Embed(` through `embed.set_footer(...)`):

```python
        embed = discord.Embed(
            title="🐳 Containers Docker",
            color=discord.Color.blue()
        )
        
        running = [c for c in containers if c.state == "running"]
        stopped = [c for c in containers if c.state != "running"]
        
        if running:
            running_list = "\n".join([f"🟢 `{c.display_name}`" for c in running[:15]])
            embed.add_field(name=f"En cours ({len(running)})", value=running_list, inline=True)
        
        if stopped:
            stopped_list = "\n".join([f"⚫ `{c.display_name}`" for c in stopped[:15]])
            embed.add_field(name=f"Arrêtés ({len(stopped)})", value=stopped_list, inline=True)
        
        if docker_manager.cache:
            embed.set_footer(text=f"Mis à jour: {docker_manager.cache.last_updated}")
```

Replace with:

```python
        embed = discord.Embed(
            title="Containers Docker",
            color=0x2C2F33,
        )

        running = [c for c in containers if c.state == "running"]
        stopped = [c for c in containers if c.state != "running"]

        if running:
            running_list = "\n".join([c.display_name for c in running[:15]])
            embed.add_field(name=f"En cours ({len(running)})", value=f"```\n{running_list}\n```", inline=True)

        if stopped:
            stopped_list = "\n".join([c.display_name for c in stopped[:15]])
            embed.add_field(name=f"Arrêtés ({len(stopped)})", value=f"```\n{stopped_list}\n```", inline=True)

        footer = "Fenrir · Docker"
        if docker_manager.cache:
            footer += f" · {docker_manager.cache.last_updated}"
        embed.set_footer(text=footer)
```

- [ ] **Step 3: Update `/stacks` embed in `src/cogs/docker.py`**

Replace:

```python
        embed = discord.Embed(
            title="📦 Stacks Docker Compose",
            description="\n".join([f"• `{s}`" for s in stacks]),
            color=discord.Color.blue()
        )
```

With:

```python
        embed = discord.Embed(
            title="Stacks Docker Compose",
            description="```\n" + "\n".join(stacks) + "\n```",
            color=0x2C2F33,
        )
        embed.set_footer(text="Fenrir · Docker")
```

- [ ] **Step 4: Update fallback embed in `src/cogs/dashboard.py`**

Replace:

```python
            await interaction.followup.send(embed=discord.Embed(
                title="📊 Dashboard",
                description=(
                    "Aucune donnée de monitoring disponible.\n\n"
                    "• Les containers Docker apparaîtront quand Docker est accessible"
                ),
                color=discord.Color.greyple()
            ))
```

With:

```python
            await interaction.followup.send(embed=discord.Embed(
                title="Dashboard",
                description="Aucune donnée disponible · Docker inaccessible",
                color=0x2C2F33,
            ))
```

- [ ] **Step 5: Commit**

```bash
git add src/cogs/downtime.py src/cogs/docker.py src/cogs/dashboard.py
git commit -m "redesign: cog embeds — scheduled-list, containers, stacks, dashboard fallback"
```

Expected: 3 files changed.

---

### Task 3: Rewrite `src/utils/webhook_server.py`

**Files:**
- Rewrite: `src/utils/webhook_server.py` (embed-related methods only — `_send_alert`, `_create_metric_bar`, `_get_metric_emoji`, `handle_generic`, `_handle_grafana_unified`, `_handle_grafana_legacy`)

The `handle_prometheus` method also builds color/emoji-prefixed titles — update that too.

- [ ] **Step 1: Add module-level `_bar()` at the top of the file**

After the imports block (after `import discord`), insert:

```python

def _bar(value: float, width: int = 10) -> str:
    """Render a fixed-width ASCII progress bar using █ and ·."""
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"

```

- [ ] **Step 2: Replace `_send_alert` method**

Replace the entire `_send_alert` method with:

```python
    async def _send_alert(
        self,
        title: str,
        description: str,
        fields: Optional[list] = None,
        source: str = "External Alert",
    ):
        """Send an alert embed to the configured channel"""
        if not self.channel_id:
            print("⚠️ Webhook received but no channel configured")
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel or not isinstance(channel, discord.abc.Messageable):
            print(f"⚠️ Channel {self.channel_id} not found")
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", "Info"),
                    value=field.get("value", "-"),
                    inline=field.get("inline", False),
                )

        embed.set_footer(text=f"Fenrir · {source}")

        await channel.send(content=self.notification_mention, embed=embed)
```

Note: add `timezone` to the existing `from datetime import datetime` import at the top of the file:
```python
from datetime import datetime, timezone
```

- [ ] **Step 3: Replace `_create_metric_bar` and `_get_metric_emoji` methods**

Delete both `_create_metric_bar` and `_get_metric_emoji` entirely. They are replaced by the module-level `_bar()`.

- [ ] **Step 4: Replace `handle_generic` method**

Replace the entire `handle_generic` method with:

```python
    async def handle_generic(self, request: web.Request) -> web.Response:
        """Handle generic webhook alerts

        Expected JSON body:
        {
            "title": "Alert Title",
            "message": "Alert description",
            "severity": "critical|warning|info",
            "service": "optional service name",
            "fields": [{"name": "...", "value": "..."}]  # optional
        }
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        title = data.get("title", "Alerte")
        message = data.get("message", "Aucun détail")
        severity = data.get("severity", "warning").lower()
        service = data.get("service")
        fields = data.get("fields", [])

        if service:
            fields.insert(0, {"name": "Service", "value": f"```\n{service}\n```", "inline": True})

        description = f"```\nSeverité : {severity.upper()}\n```\n{message}" if severity else message

        await self._send_alert(
            title=title,
            description=description,
            fields=fields,
            source="Generic Webhook",
        )

        return web.json_response({"status": "ok", "message": "Alert sent"})
```

- [ ] **Step 5: Replace `handle_prometheus` method**

Replace the entire `handle_prometheus` method with:

```python
    async def handle_prometheus(self, request: web.Request) -> web.Response:
        """Handle Prometheus Alertmanager webhooks

        Prometheus Alertmanager sends alerts in this format:
        {
            "status": "firing|resolved",
            "alerts": [{
                "status": "firing",
                "labels": {"alertname": "...", "severity": "..."},
                "annotations": {"summary": "...", "description": "..."}
            }]
        }
        """
        if not self._verify_token(request):
            return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        alerts = data.get("alerts", [])

        for alert in alerts:
            status = alert.get("status", "unknown")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})

            alert_name = labels.get("alertname", "Unknown Alert")
            severity = labels.get("severity", "warning")
            summary = annotations.get("summary", "")
            description = annotations.get("description", "No description")

            state_label = "RESOLVED" if status == "resolved" else "FIRING"
            title = f"[{state_label}] {alert_name}"

            fields = []
            if summary:
                fields.append({"name": "Résumé", "value": summary, "inline": False})
            for key in ["instance", "job", "service"]:
                if key in labels:
                    fields.append({"name": key.title(), "value": f"```\n{labels[key]}\n```", "inline": True})

            await self._send_alert(
                title=title,
                description=f"```\nSévérité : {severity.upper()}\n```\n{description}",
                fields=fields,
                source="Prometheus",
            )

        return web.json_response({"status": "ok", "alerts_processed": len(alerts)})
```

- [ ] **Step 6: Replace `_handle_grafana_unified` method**

Replace the entire `_handle_grafana_unified` method with:

```python
    async def _handle_grafana_unified(self, data: dict) -> web.Response:
        """Handle Grafana Unified Alerting (Grafana 8+)

        Format:
        {
            "alerts": [{
                "status": "firing|resolved",
                "labels": {"alertname": "...", "severity": "..."},
                "annotations": {"summary": "...", "description": "..."},
                "values": {"A": 92.5}
            }],
            "commonLabels": {...},
            "externalURL": "..."
        }
        """
        alerts = data.get("alerts", [])
        external_url = data.get("externalURL", "")

        for alert in alerts:
            status = alert.get("status", "firing")
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            values = alert.get("values", {})

            alert_name = labels.get("alertname", "Grafana Alert")
            severity = labels.get("severity", "warning")
            instance = labels.get("instance", "")
            summary = annotations.get("summary", "")
            description = annotations.get("description", "")

            state_label = "RESOLVED" if status == "resolved" else severity.upper()
            title = f"[{state_label}] {alert_name}"

            bar_lines = []
            for key, value in values.items():
                if isinstance(value, (int, float)) and 0 <= value <= 100:
                    bar_lines.append(f"{key:<12} {_bar(value)}  {value:.1f}%")
                else:
                    bar_lines.append(f"{key}: {value}")

            text_parts = []
            if summary:
                text_parts.append(summary)
            if description and description != summary:
                text_parts.append(description)

            parts = []
            if bar_lines:
                parts.append("```\n" + "\n".join(bar_lines) + "\n```")
            if text_parts:
                parts.append("\n".join(text_parts))
            full_description = "\n".join(parts) if parts else "Aucun détail"

            fields = []
            if instance:
                fields.append({"name": "Instance", "value": f"```\n{instance}\n```", "inline": True})
            if external_url:
                fields.append({"name": "Dashboard", "value": f"[Grafana]({external_url})", "inline": True})

            await self._send_alert(
                title=title,
                description=full_description,
                fields=fields,
                source="Grafana",
            )

        return web.json_response({"status": "ok", "alerts_processed": len(alerts)})
```

- [ ] **Step 7: Replace `_handle_grafana_legacy` method**

Replace the entire `_handle_grafana_legacy` method with:

```python
    async def _handle_grafana_legacy(self, data: dict) -> web.Response:
        """Handle legacy Grafana alerting format"""
        title = data.get("title", data.get("ruleName", "Grafana Alert"))
        message = data.get("message", "No message")
        state = data.get("state", "alerting")
        eval_matches = data.get("evalMatches", [])
        rule_url = data.get("ruleUrl", "")

        state_label = {
            "ok": "RESOLVED",
            "alerting": "FIRING",
            "no_data": "NO DATA",
        }.get(state, "PENDING")
        title_str = f"[{state_label}] {title}"

        bar_lines = []
        for match in eval_matches[:5]:
            metric = match.get("metric", "Value")
            value = match.get("value", 0)
            if isinstance(value, (int, float)) and 0 <= value <= 100:
                bar_lines.append(f"{metric:<12} {_bar(value)}  {value:.1f}%")
            else:
                bar_lines.append(f"{metric}: {value}")

        parts = []
        if bar_lines:
            parts.append("```\n" + "\n".join(bar_lines) + "\n```")
        if message and message != title:
            parts.append(message)
        full_description = "\n".join(parts) if parts else "Aucun détail"

        fields = []
        if rule_url:
            fields.append({"name": "Dashboard", "value": f"[Grafana]({rule_url})", "inline": True})

        await self._send_alert(
            title=title_str,
            description=full_description,
            fields=fields,
            source="Grafana",
        )

        return web.json_response({"status": "ok"})
```

- [ ] **Step 8: Commit**

```bash
git add src/utils/webhook_server.py
git commit -m "redesign: webhook_server — strip emoji/color logic, use _bar() and static color"
```

Expected: 1 file changed.

---

### Task 4: Update `src/utils/helpers.py`

**Files:**
- Modify: `src/utils/helpers.py` (create_error_embed, create_success_embed, create_info_embed)

- [ ] **Step 1: Replace the three embed helpers**

In `src/utils/helpers.py`, replace:

```python
def create_error_embed(
    title: str = "❌ Erreur",
    description: str = "Une erreur est survenue.",
    error: Optional[Exception] = None
) -> discord.Embed:
    """Create a standardized error embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xFF4444,
        timestamp=datetime.now()
    )
    
    if error:
        error_msg = str(error)[:200]
        embed.add_field(name="Détails", value=f"```\n{error_msg}\n```", inline=False)
    
    embed.set_footer(text="🐺 Fenrir")
    return embed


def create_success_embed(
    title: str = "✅ Succès",
    description: str = "Opération réussie."
) -> discord.Embed:
    """Create a standardized success embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x44FF44,
        timestamp=datetime.now()
    )


def create_info_embed(
    title: str,
    description: str = ""
) -> discord.Embed:
    """Create a standardized info embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x5865F2,
        timestamp=datetime.now()
    )
```

With:

```python
def create_error_embed(
    title: str = "Erreur",
    description: str = "Une erreur est survenue.",
    error: Optional[Exception] = None,
) -> discord.Embed:
    """Create a standardized error embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )
    if error:
        embed.add_field(name="Détails", value=f"```\n{str(error)[:200]}\n```", inline=False)
    embed.set_footer(text="Fenrir")
    return embed


def create_success_embed(
    title: str = "Succès",
    description: str = "Opération réussie.",
) -> discord.Embed:
    """Create a standardized success embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )


def create_info_embed(
    title: str,
    description: str = "",
) -> discord.Embed:
    """Create a standardized info embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )
```

`timezone` is already imported on line 5 of helpers.py (`from datetime import datetime, timedelta, timezone`), so no import change needed.

- [ ] **Step 2: Commit**

```bash
git add src/utils/helpers.py
git commit -m "redesign: helpers — uniform 0x2C2F33 colour, no emoji defaults, timezone-aware"
```

Expected: 1 file changed.

---

### Task 5: Build, deploy and verify

- [ ] **Step 1: Merge branch to dev and build**

```bash
cd /srv/project/python/FenrirBot
git checkout dev
git merge feature/embed-global-redesign
./build.sh
```

Expected: `✓ fenrirbot:latest built`

- [ ] **Step 2: Redeploy**

```bash
cd /srv/nebula
./scripts/start-docker.sh recreate management
```

Expected: `Container fenrirbot Started`

- [ ] **Step 3: Check logs**

```bash
docker logs fenrirbot --tail 20
```

Expected: all 6 cogs loaded, `✅ Synced N slash command(s)`

- [ ] **Step 4: Verify in Discord**

- `/downtime` → dark embed, no GIF, no emoji in title, author in footer
- `/up` → same style, `OPERATIONNEL` in code block
- `/maintenance` → dark embed, type + duration fields in code blocks
- `/scheduled` → dark embed, date + type + duration + details fields
- `/status` → simple dark embed with message
- `/scheduled-list` → dark embed, code-block field per item
- `/containers` → dark embed, code-block lists
- `/stacks` → dark embed, code-block list
- `/dashboard` → dark embed, ASCII bar in description

- [ ] **Step 5: Commit plan file**

```bash
cd /srv/project/python/FenrirBot
git add docs/superpowers/plans/2026-04-21-embed-global-redesign.md
git commit -m "docs: add global embed redesign implementation plan"
```
