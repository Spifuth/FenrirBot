# Remove Dead Monitoring Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all code that depends on Netdata and UptimeKuma, neither of which is deployed in the current stack.

**Architecture:** The stack replaced Netdata with VictoriaMetrics+Grafana+Alloy, and UptimeKuma was never deployed. This leaves two full cogs dead (`netdata`, `reports`), four commands dead in `status`, one command dead in `dashboard`, and UptimeKuma pause/resume hooks silently failing across `downtime`, `views`, and `webhook_server`. The cleanup removes ~900 lines of code touching 10 files with no behavioural regressions on working features.

**Tech Stack:** Python 3.11+, discord.py 2.x, aiohttp — no new dependencies added or removed.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Delete | `src/cogs/netdata.py` | Entire file gone |
| Delete | `src/cogs/reports.py` | Entire file gone |
| Delete | `src/utils/uptimekuma.py` | Entire file gone (Task 7, after all consumers cleaned) |
| Modify | `src/bot.py` | Remove 2 cog registrations + UptimeKuma init block |
| Modify | `src/cogs/status.py` | Remove 4 commands, remove uptimekuma import |
| Modify | `src/cogs/dashboard.py` | Remove UptimeKuma embed + `/uptime` command |
| Modify | `src/cogs/downtime.py` | Remove pause/resume integration throughout |
| Modify | `src/utils/views.py` | Remove UptimeKuma params + resume logic |
| Modify | `src/utils/webhook_server.py` | Remove 2 routes + 2 handler methods |
| Modify | `src/utils/helpers.py` | Remove 3 dead helper functions |
| Modify | `src/utils/embeds.py` | Remove `DashboardEmbed.uptimekuma_status` |
| Modify | `src/config.py` | Remove 9 dead config fields |

---

## Task 1: Delete dead cogs and update bot.py

**Files:**
- Delete: `src/cogs/netdata.py`
- Delete: `src/cogs/reports.py`
- Modify: `src/bot.py`

- [ ] **Step 1: Delete the two dead cog files**

```bash
rm /srv/project/python/FenrirBot/src/cogs/netdata.py
rm /srv/project/python/FenrirBot/src/cogs/reports.py
```

- [ ] **Step 2: Update `src/bot.py`**

Replace the entire file with:

```python
"""Fenrir Bot - Main bot class and initialization"""

import discord
from discord.ext import commands
from typing import Optional

from .config import config
from .utils.webhook_server import WebhookServer


class FenrirBot(commands.Bot):
    """Main bot class for Fenrir"""

    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
    ]

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=config.command_prefix if config else "!",
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )

        self.webhook_server: Optional[WebhookServer] = None

        if config and config.webhook_enabled:
            self.webhook_server = WebhookServer(
                bot=self,
                host=config.webhook_host,
                port=config.webhook_port,
                secret_token=config.webhook_secret or None
            )

    async def setup_hook(self):
        """Called when the bot is starting up - load cogs here"""
        for cog in self.INITIAL_COGS:
            try:
                await self.load_extension(cog)
                print(f"  ✅ Loaded: {cog}")
            except Exception as e:
                print(f"  ❌ Failed to load {cog}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"  ✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  ❌ Failed to sync commands: {e}")

    async def on_ready(self):
        """Called when the bot is fully connected and ready"""
        print(f"\n🐺 Fenrir is online!")
        print(f"   User: {self.user}")
        print(f"   Guilds: {len(self.guilds)}")
        print(f"   Prefix: {self.command_prefix}")
        if config and config.announcement_channel_id:
            print(f"   Announcement Channel: {config.announcement_channel_id}")

        if self.webhook_server and config:
            self.webhook_server.set_channel(config.announcement_channel_id)
            if config.notification_role_id:
                self.webhook_server.set_mention(f"<@&{config.notification_role_id}>")
            await self.webhook_server.start()
            print(f"   Webhook Server: http://{config.webhook_host}:{config.webhook_port}")
        print()

    async def close(self):
        """Cleanup when bot is shutting down"""
        if self.webhook_server:
            await self.webhook_server.stop()
        await super().close()


def create_bot() -> FenrirBot:
    """Factory function to create a configured bot instance"""
    return FenrirBot()
```

- [ ] **Step 3: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/bot.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /srv/project/python/FenrirBot
git add -A
git commit -m "remove: delete netdata and reports cogs, drop UptimeKuma init from bot"
```

---

## Task 2: Strip UptimeKuma commands from `cogs/status.py`

**Files:**
- Modify: `src/cogs/status.py`

The four commands `/monitors`, `/monitor`, `/pause`, `/resume` all call `uptimekuma_module.uptimekuma_auth_client` which no longer exists. Keep only `/status`, `/ping`, and the prefix `!status`.

- [ ] **Step 1: Replace `src/cogs/status.py` with the cleaned version**

```python
"""Status and utility commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..utils.embeds import DowntimeEmbed
from ..utils.helpers import get_announcement_channel, get_notification_mention
from ..config import config


class StatusCog(commands.Cog, name="Status"):
    """Commands for status updates and bot info"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="status", description="Envoyer une mise à jour de statut")
    @app_commands.describe(
        message="Message de statut à envoyer",
        mention="Mentionner le rôle de notification (défaut: Non)"
    )
    async def status_slash(self, interaction: discord.Interaction, message: str, mention: bool = False):
        """Send a status update via slash command"""
        channel = get_announcement_channel(self.bot, interaction.channel)
        embed = DowntimeEmbed.status(message, interaction.user)
        assert channel is not None
        await channel.send(
            content=get_notification_mention() if mention else None,
            embed=embed
        )
        await interaction.response.send_message("✅ Mise à jour envoyée", ephemeral=True)

    @app_commands.command(name="ping", description="Vérifier si le bot répond")
    async def ping_slash(self, interaction: discord.Interaction):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! Latence: {latency}ms", ephemeral=True)

    @commands.command(name="status")
    async def status_prefix(self, ctx: commands.Context, *, message: str):
        """Quick status update: !status Everything is fine"""
        channel = get_announcement_channel(self.bot, ctx.channel)
        embed = DowntimeEmbed.status(message, ctx.author)
        assert channel is not None
        await channel.send(embed=embed)
        await ctx.message.add_reaction("✅")


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(StatusCog(bot))
```

- [ ] **Step 2: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/cogs/status.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/cogs/status.py
git commit -m "remove: strip UptimeKuma monitor commands from status cog"
```

---

## Task 3: Strip UptimeKuma from `cogs/dashboard.py`

**Files:**
- Modify: `src/cogs/dashboard.py`

Remove the UptimeKuma embed section from `/dashboard` and the entire `/uptime` command. The Docker embed stays untouched.

- [ ] **Step 1: Replace `src/cogs/dashboard.py` with the cleaned version**

```python
"""Dashboard and monitoring commands"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ..utils.docker import docker_manager
from ..utils.embeds import DashboardEmbed


class DashboardCog(commands.Cog, name="Dashboard"):
    """Commands for status dashboard and monitoring"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dashboard", description="📊 Afficher le tableau de bord des services")
    async def dashboard_slash(self, interaction: discord.Interaction):
        """Display a comprehensive status dashboard"""
        await interaction.response.defer()

        containers = docker_manager.get_containers(include_stopped=True)

        if not containers:
            await interaction.followup.send(embed=discord.Embed(
                title="📊 Dashboard",
                description=(
                    "Aucune donnée de monitoring disponible.\n\n"
                    "• Les containers Docker apparaîtront quand Docker est accessible"
                ),
                color=discord.Color.greyple()
            ))
            return

        running = [c for c in containers if c.state == "running"]
        stopped = [c for c in containers if c.state != "running"]
        docker_embed = DashboardEmbed.docker_status(containers, running, stopped)
        await interaction.followup.send(embed=docker_embed)


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DashboardCog(bot))
```

- [ ] **Step 2: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/cogs/dashboard.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/cogs/dashboard.py
git commit -m "remove: strip UptimeKuma section from dashboard, drop /uptime command"
```

---

## Task 4: Strip UptimeKuma from `utils/views.py`

**Files:**
- Modify: `src/utils/views.py`

Remove the `uptimekuma_paused`/`uptimekuma_monitor_id` constructor params and both resume blocks inside `restore_button` and `cancel_button`.

- [ ] **Step 1: Replace `src/utils/views.py` with the cleaned version**

```python
"""Interactive views (buttons, modals) for Fenrir Bot"""

import discord
from discord import ui
from datetime import datetime, timedelta
import asyncio
import re
from typing import Optional

from .embeds import DowntimeEmbed, ServiceType


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse a duration string like '30 minutes', '2 hours', '1h30m' into timedelta"""
    duration_str = duration_str.lower().strip()

    total_seconds = 0

    hours_match = re.search(r'(\d+)\s*(?:hours?|h)', duration_str)
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600

    mins_match = re.search(r'(\d+)\s*(?:minutes?|mins?|m(?!o))', duration_str)
    if mins_match:
        total_seconds += int(mins_match.group(1)) * 60

    secs_match = re.search(r'(\d+)\s*(?:seconds?|secs?|s)', duration_str)
    if secs_match:
        total_seconds += int(secs_match.group(1))

    if total_seconds > 0:
        return timedelta(seconds=total_seconds)

    return None


class DowntimeView(ui.View):
    """Interactive view for downtime announcements with restore button"""

    def __init__(
        self,
        service: str,
        author_id: int,
        duration_str: str = "Unknown",
        announcement_channel: Optional[discord.abc.Messageable] = None,
        notification_mention: Optional[str] = "@here",
        service_type: ServiceType = ServiceType.OTHER,
    ):
        super().__init__(timeout=86400)
        self.service = service
        self.author_id = author_id
        self.duration_str = duration_str
        self.announcement_channel = announcement_channel
        self.notification_mention = notification_mention
        self.service_type = service_type
        self.resolved = False
        self.message: Optional[discord.Message] = None
        self.timer_task: Optional[asyncio.Task] = None
        self.incident_thread: Optional[discord.Thread] = None

        self.duration = parse_duration(duration_str)
        self.start_time = datetime.now()

    async def start_timer(self):
        """Start a background timer that reminds when duration is up"""
        if not self.duration:
            return

        async def timer_callback():
            try:
                await asyncio.sleep(self.duration.total_seconds())

                if not self.resolved and self.message:
                    await self.message.reply(
                        f"⏰ **Reminder:** The estimated downtime for **{self.service}** "
                        f"({self.duration_str}) has elapsed!\n"
                        f"<@{self.author_id}> - Click the button below to mark as restored, "
                        f"or ignore if still in progress."
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Timer error: {e}")

        self.timer_task = asyncio.create_task(timer_callback())

    @ui.button(label="✅ Service Restored", style=discord.ButtonStyle.green)
    async def restore_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to mark service as restored"""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can mark it as restored.",
                ephemeral=True
            )
            return

        self.resolved = True

        if self.timer_task:
            self.timer_task.cancel()

        actual_duration = datetime.now() - self.start_time
        hours, remainder = divmod(int(actual_duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            duration_text = f"{hours}h {minutes}m"
        elif minutes > 0:
            duration_text = f"{minutes}m {seconds}s"
        else:
            duration_text = f"{seconds}s"

        button.disabled = True
        button.label = f"✅ Restored after {duration_text}"
        button.style = discord.ButtonStyle.gray

        assert interaction.message is not None
        await interaction.message.edit(view=self)

        embed = DowntimeEmbed.end(self.service, interaction.user, self.service_type)
        embed.add_field(name="⏱️ Actual Downtime", value=duration_text, inline=True)

        channel = self.announcement_channel or interaction.channel
        assert channel is not None
        await channel.send(embed=embed)

        if self.incident_thread:
            await self.incident_thread.send(
                f"✅ **Incident Resolved**\n\n"
                f"**Service:** {self.service}\n"
                f"**Duration:** {duration_text}\n"
                f"**Resolved by:** {interaction.user.mention}\n\n"
                f"*This thread will be archived.*"
            )
            await self.incident_thread.edit(archived=True, locked=True)

        await interaction.response.send_message(
            f"✅ **{self.service}** marked as restored!",
            ephemeral=True
        )

        self.stop()

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to cancel/dismiss the downtime (false alarm)"""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can cancel it.",
                ephemeral=True
            )
            return

        self.resolved = True

        if self.timer_task:
            self.timer_task.cancel()

        for child in self.children:
            child.disabled = True

        assert interaction.message is not None
        await interaction.message.edit(
            content=f"~~{interaction.message.content or ''}~~ **[CANCELLED]**",
            view=self
        )

        await interaction.response.send_message(
            f"🚫 Downtime announcement for **{self.service}** has been cancelled.",
            ephemeral=True
        )

        if self.incident_thread:
            await self.incident_thread.send("🚫 *Incident cancelled - false alarm*")
            await self.incident_thread.edit(archived=True)

        self.stop()

    async def on_timeout(self):
        """Called when the view times out (24h)"""
        if self.message and not self.resolved:
            for child in self.children:
                child.disabled = True

            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
```

- [ ] **Step 2: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/utils/views.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/utils/views.py
git commit -m "remove: strip UptimeKuma pause/resume from DowntimeView"
```

---

## Task 5: Strip UptimeKuma from `cogs/downtime.py`

**Files:**
- Modify: `src/cogs/downtime.py`

Remove `_init_uptimekuma_client`, `_pause_uptimekuma_monitor`, `monitor_autocomplete`, all UptimeKuma kwargs passed to `DowntimeView`, and the `resume_monitor` logic in `/up`. The `DowntimeView` constructor signature changed in Task 4 — this task must come after Task 4.

- [ ] **Step 1: Remove the uptimekuma import at the top of downtime.py**

Find and remove:
```python
from ..utils import uptimekuma as uptimekuma_module
```

- [ ] **Step 2: Remove `_init_uptimekuma_client` call and method**

In `__init__`, remove:
```python
        # Initialize UptimeKuma authenticated client for pause/resume
        self._init_uptimekuma_client()
```

Remove the entire `_init_uptimekuma_client` method:
```python
    def _init_uptimekuma_client(self):
        """Initialize UptimeKuma authenticated client if credentials are available"""
        if config and config.uptimekuma_url and config.uptimekuma_username and config.uptimekuma_password:
            uptimekuma_module.init_uptimekuma_auth(
                config.uptimekuma_url,
                config.uptimekuma_username,
                config.uptimekuma_password
            )
            print("[Downtime] UptimeKuma auth client initialized for auto-pause/resume")
        else:
            print("[Downtime] UptimeKuma auth not configured (missing URL/username/password)")
```

- [ ] **Step 3: Remove `_pause_uptimekuma_monitor` method**

Remove the entire method (lines 266–288 in the original):
```python
    async def _pause_uptimekuma_monitor(self, service_name: str) -> tuple[bool, Optional[int]]:
        """
        Pause UptimeKuma monitor for a service if auto-pause is enabled
        ...
        """
        ...
```

- [ ] **Step 4: Remove `monitor_autocomplete` method**

Remove the entire method (lines 371–401):
```python
    async def monitor_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for Uptime Kuma monitors"""
        ...
```

- [ ] **Step 5: Clean `_trigger_scheduled_downtime`**

Remove the UptimeKuma auto-pause block and clean kwargs. Replace the UptimeKuma section:

```python
        # Auto-pause UptimeKuma monitor if enabled
        uptimekuma_paused = False
        uptimekuma_monitor_id = None
        if config and config.uptimekuma_auto_pause:
            uptimekuma_paused, uptimekuma_monitor_id = await self._pause_uptimekuma_monitor(maintenance.service)
```
with nothing (delete those 4 lines).

Replace the DowntimeView construction in `_trigger_scheduled_downtime`:
```python
        view = DowntimeView(
            service=maintenance.service,
            author_id=maintenance.author_id,
            duration_str=maintenance.duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=service_type,
            uptimekuma_paused=uptimekuma_paused,
            uptimekuma_monitor_id=uptimekuma_monitor_id
        )
```
with:
```python
        view = DowntimeView(
            service=maintenance.service,
            author_id=maintenance.author_id,
            duration_str=maintenance.duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=service_type,
        )
```

Remove the `uptimekuma_note` lines and its reference in the thread message:
```python
        uptimekuma_note = ""
        if uptimekuma_paused:
            uptimekuma_note = f"\n⏸️ **UptimeKuma:** Monitor paused (ID: {uptimekuma_monitor_id})"
```
and in the thread send call, remove `f"{uptimekuma_note}"` from the f-string.

- [ ] **Step 6: Clean `downtime_slash`**

Remove `pause_monitor: Optional[bool] = None` parameter from the command signature.

Remove the `@app_commands.describe` entry for `pause_monitor`.

Remove these lines from the body:
```python
        # Auto-pause UptimeKuma monitor if enabled
        uptimekuma_paused = False
        uptimekuma_monitor_id = None
        should_pause = pause_monitor if pause_monitor is not None else (config and config.uptimekuma_auto_pause)
        
        if should_pause:
            uptimekuma_paused, uptimekuma_monitor_id = await self._pause_uptimekuma_monitor(service)
```

Replace the DowntimeView construction:
```python
        view = DowntimeView(
            service=service,
            author_id=interaction.user.id,
            duration_str=duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=svc_type,
            uptimekuma_paused=uptimekuma_paused,
            uptimekuma_monitor_id=uptimekuma_monitor_id
        )
```
with:
```python
        view = DowntimeView(
            service=service,
            author_id=interaction.user.id,
            duration_str=duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=svc_type,
        )
```

Simplify `response_parts` — remove the UptimeKuma conditional:
```python
        if uptimekuma_paused:
            response_parts.insert(1, f"⏸️ Monitoring UptimeKuma mis en pause (ID: {uptimekuma_monitor_id})")
```

- [ ] **Step 7: Clean `up_slash`**

Remove `resume_monitor: bool = True` parameter.

Remove its `@app_commands.describe` entry.

Remove the UptimeKuma resume block:
```python
        # Resume UptimeKuma monitor if requested
        uptimekuma_resumed = False
        if resume_monitor and uptimekuma_module.uptimekuma_auth_client:
            try:
                await uptimekuma_module.uptimekuma_auth_client.connect()
                success, monitor_id = await uptimekuma_module.uptimekuma_auth_client.resume_monitor_by_name(service)
                uptimekuma_resumed = success
                if success:
                    print(f"[Downtime] Resumed UptimeKuma monitor for '{service}' (ID: {monitor_id})")
            except Exception as e:
                print(f"[Downtime] Error resuming UptimeKuma monitor: {e}")
```

Simplify the response:
```python
        response = f"✅ Annonce de restauration envoyée pour **{service}** ({service_type.label})"
        if uptimekuma_resumed:
            response += "\n▶️ Monitoring UptimeKuma repris"
```
becomes:
```python
        response = f"✅ Annonce de restauration envoyée pour **{service}** ({service_type.label})"
```

- [ ] **Step 8: Clean `maintenance_slash`** (same pattern as `downtime_slash`)

Remove `pause_monitor: Optional[bool] = None` parameter and its `@app_commands.describe` entry.

Remove the UptimeKuma pause block (identical pattern to Step 6).

Replace DowntimeView kwargs to remove `uptimekuma_paused` and `uptimekuma_monitor_id`.

Remove the `if uptimekuma_paused:` line from `response_parts`.

- [ ] **Step 9: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/cogs/downtime.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 10: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/cogs/downtime.py
git commit -m "remove: strip UptimeKuma pause/resume integration from downtime cog"
```

---

## Task 6: Remove dead webhook handlers from `utils/webhook_server.py`

**Files:**
- Modify: `src/utils/webhook_server.py`

Remove the `/webhook/uptimekuma` and `/webhook/netdata` routes and their handler methods. The generic, prometheus, and grafana handlers remain — Grafana is deployed and the handler is ready to use.

- [ ] **Step 1: Remove the two dead routes from `__init__`**

Find in `__init__`:
```python
        self.app.router.add_post("/webhook/uptimekuma", self.handle_uptimekuma)
        self.app.router.add_post("/webhook/netdata", self.handle_netdata)
```
Delete both lines.

- [ ] **Step 2: Remove `handle_uptimekuma` method**

Delete the entire method from line 468 to 529 (inclusive). It starts with:
```python
    async def handle_uptimekuma(self, request: web.Request) -> web.Response:
        """Handle UptimeKuma webhook notifications
```
and ends with:
```python
        return web.json_response({"status": "ok"})
```
(the one following `await self._send_alert(...)` for UptimeKuma).

- [ ] **Step 3: Remove `handle_netdata` method**

Delete the entire method from line 531 to the end of the file (line 644). It starts with:
```python
    async def handle_netdata(self, request: web.Request) -> web.Response:
        """Handle Netdata webhook notifications
```

- [ ] **Step 4: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/utils/webhook_server.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/utils/webhook_server.py
git commit -m "remove: drop UptimeKuma and Netdata webhook handlers"
```

---

## Task 7: Delete `utils/uptimekuma.py`

**Files:**
- Delete: `src/utils/uptimekuma.py`

All consumers have been cleaned in Tasks 2–6. Verify there are no remaining imports before deleting.

- [ ] **Step 1: Verify no remaining imports of uptimekuma**

```bash
grep -r "uptimekuma" /srv/project/python/FenrirBot/src/ --include="*.py"
```

Expected: no output. If any file still imports from uptimekuma, fix it before proceeding.

- [ ] **Step 2: Delete the file**

```bash
rm /srv/project/python/FenrirBot/src/utils/uptimekuma.py
```

- [ ] **Step 3: Verify the package still imports cleanly**

```bash
cd /srv/project/python/FenrirBot && python -c "import src.bot" 2>&1 | head -20
```

Expected: only Discord/asyncio startup noise, no `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 4: Commit**

```bash
cd /srv/project/python/FenrirBot
git add -A
git commit -m "remove: delete utils/uptimekuma.py — no longer used anywhere"
```

---

## Task 8: Clean dead helpers from `utils/helpers.py`

**Files:**
- Modify: `src/utils/helpers.py`

Remove three functions that exist only to support the deleted integrations: `get_reports_channel` (used only by the deleted `reports.py`), `is_netdata_configured` (used only by the deleted `netdata.py`), and `is_uptimekuma_configured` (used only by the deleted `dashboard.py` and `status.py` UptimeKuma commands).

- [ ] **Step 1: Remove `get_reports_channel`**

Delete lines 36–40:
```python
def get_reports_channel(bot: discord.Client) -> Optional[discord.TextChannel]:
    """Get the configured reports channel"""
    if config and config.reports_channel_id:
        return bot.get_channel(config.reports_channel_id)
    return None
```

- [ ] **Step 2: Remove `is_netdata_configured`**

Delete lines 317–319:
```python
def is_netdata_configured() -> bool:
    """Check if Netdata is properly configured"""
    return bool(get_config_value('netdata_url', ''))
```

- [ ] **Step 3: Remove `is_uptimekuma_configured`**

Delete lines 322–324:
```python
def is_uptimekuma_configured() -> bool:
    """Check if UptimeKuma is properly configured"""
    return bool(get_config_value('uptimekuma_url', ''))
```

- [ ] **Step 4: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/utils/helpers.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/utils/helpers.py
git commit -m "remove: drop dead helper functions for Netdata and UptimeKuma"
```

---

## Task 9: Remove `DashboardEmbed.uptimekuma_status` from `utils/embeds.py`

**Files:**
- Modify: `src/utils/embeds.py`

`DashboardEmbed.docker_status` is still used by the cleaned `dashboard.py`. `DashboardEmbed.uptimekuma_status` has no callers anymore.

- [ ] **Step 1: Remove `uptimekuma_status` from `DashboardEmbed`**

Delete lines 535–574 — the entire `uptimekuma_status` static method:
```python
    @staticmethod
    def uptimekuma_status(monitors: list, up_count: int, down_count: int) -> discord.Embed:
        """Create an UptimeKuma status embed"""
        ...
        return embed
```

- [ ] **Step 2: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/utils/embeds.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/utils/embeds.py
git commit -m "remove: drop DashboardEmbed.uptimekuma_status — no callers remain"
```

---

## Task 10: Remove dead config fields from `src/config.py`

**Files:**
- Modify: `src/config.py`

Remove 9 config fields that only existed to configure Netdata and UptimeKuma.

- [ ] **Step 1: Replace `src/config.py` with the cleaned version**

```python
"""Bot configuration management"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


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

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in environment variables")

        channel_id = os.getenv("ANNOUNCEMENT_CHANNEL_ID", "0")
        role_id = os.getenv("NOTIFICATION_ROLE_ID", "0")

        return cls(
            token=token,
            announcement_channel_id=int(channel_id),
            notification_role_id=int(role_id),
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
            webhook_enabled=os.getenv("WEBHOOK_ENABLED", "false").lower() == "true",
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=int(os.getenv("WEBHOOK_PORT", "8085")),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        )


config = Config.from_env() if os.getenv("DISCORD_TOKEN") else None
```

- [ ] **Step 2: Verify syntax**

```bash
cd /srv/project/python/FenrirBot && python -m py_compile src/config.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Full import check — verify no remaining dead references**

```bash
grep -r "uptimekuma\|netdata\|reports_channel\|UPTIMEKUMA\|NETDATA\|REPORTS_CHANNEL" \
  /srv/project/python/FenrirBot/src/ --include="*.py"
```

Expected: no output.

- [ ] **Step 4: Verify all remaining cogs compile**

```bash
cd /srv/project/python/FenrirBot && \
  python -m py_compile src/config.py && \
  python -m py_compile src/bot.py && \
  python -m py_compile src/cogs/downtime.py && \
  python -m py_compile src/cogs/status.py && \
  python -m py_compile src/cogs/docker.py && \
  python -m py_compile src/cogs/dashboard.py && \
  python -m py_compile src/utils/views.py && \
  python -m py_compile src/utils/embeds.py && \
  python -m py_compile src/utils/helpers.py && \
  python -m py_compile src/utils/webhook_server.py && \
  echo "ALL OK"
```

Expected: `ALL OK`

- [ ] **Step 5: Commit**

```bash
cd /srv/project/python/FenrirBot
git add src/config.py
git commit -m "remove: drop Netdata, UptimeKuma, and reports config fields"
```
