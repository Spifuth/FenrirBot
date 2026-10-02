# Merge `/downtime` into `/maintenance` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `/downtime` command and prefix commands `!down`/`!up`, making `/maintenance` the single announce command with `maintenance_type` always required; restore button label and restore embed title adapt dynamically to the selected type.

**Architecture:** Three files change in dependency order — `embeds.py` first (adds param to `end()`), then `views.py` (consumes it via new `maintenance_type` param), then `downtime.py` (removes dead commands, threads `maintenance_type` through all callers). `DowntimeEmbed.start()` becomes dead code after `downtime.py` is updated and is removed in the same task.

**Tech Stack:** Python 3.11+, discord.py 2.x, `discord.ui.View`

---

## File Map

| File | Change |
|---|---|
| `src/utils/embeds.py` | Add `maintenance_type` param to `end()`; remove dead `start()` (in Task 3) |
| `src/utils/views.py` | Add `maintenance_type: MaintenanceType` to `DowntimeView`; set button label dynamically; pass type to `end()` |
| `src/cogs/downtime.py` | Remove `downtime_slash`, `down_prefix`, `up_prefix`; add DOWNTIME choice to `/maintenance`; pass `maintenance_type` to `DowntimeView` everywhere; collapse `_trigger_scheduled_downtime` if/else |

---

### Task 1: `embeds.py` — type-aware `end()`

**Files:**
- Modify: `src/utils/embeds.py:123-137`

- [ ] **Step 1: Update `DowntimeEmbed.end()` signature and body**

Replace the current `end()` method (lines 123–137) with:

```python
@staticmethod
def end(
    service: str,
    author: discord.User | discord.Member,
    service_type: ServiceType = ServiceType.OTHER,
    maintenance_type: MaintenanceType | None = None,
) -> discord.Embed:
    if maintenance_type is None or maintenance_type == MaintenanceType.DOWNTIME:
        title = f"Service rétabli · {service}"
    else:
        title = f"{maintenance_type.label} terminée · {service}"
    embed = discord.Embed(
        title=title,
        description=f"{service_type.label} opérationnel",
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Statut", value="```\nOPERATIONNEL\n```", inline=True)
    embed.set_footer(text=f"Fenrir · Downtime · {author.display_name}")
    return embed
```

`maintenance_type` defaults to `None` so the existing `/up` slash command caller requires no change.

- [ ] **Step 2: Verify no syntax errors**

```bash
cd /srv/project/python/FenrirBot && source venv/bin/activate && python -c "from src.utils.embeds import DowntimeEmbed, MaintenanceType, ServiceType; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/utils/embeds.py
git commit -m "feat(embeds): maintenance_type param on end() for type-aware restore title"
```

---

### Task 2: `views.py` — dynamic restore button label

**Files:**
- Modify: `src/utils/views.py`

- [ ] **Step 1: Update the import line**

Current line 10:
```python
from .embeds import DowntimeEmbed, ServiceType
```

Replace with:
```python
from .embeds import DowntimeEmbed, MaintenanceType, ServiceType
```

- [ ] **Step 2: Add `maintenance_type` param to `DowntimeView.__init__` and set the button label dynamically**

Current `__init__` signature (line 40–48):
```python
def __init__(
    self,
    service: str,
    author_id: int,
    duration_str: str = "Unknown",
    announcement_channel: Optional[discord.abc.Messageable] = None,
    notification_mention: Optional[str] = "@here",
    service_type: ServiceType = ServiceType.OTHER,
):
```

Replace with:
```python
def __init__(
    self,
    service: str,
    author_id: int,
    duration_str: str = "Unknown",
    announcement_channel: Optional[discord.abc.Messageable] = None,
    notification_mention: Optional[str] = "@here",
    service_type: ServiceType = ServiceType.OTHER,
    maintenance_type: MaintenanceType = MaintenanceType.DOWNTIME,
):
```

Then add these two lines inside `__init__`, after `self.service_type = service_type`:
```python
self.maintenance_type = maintenance_type
self.restore_button.label = {
    MaintenanceType.DOWNTIME:   "✅ Service restauré",
    MaintenanceType.UPDATE:     "✅ Mise à jour terminée",
    MaintenanceType.BACKUP:     "✅ Sauvegarde terminée",
    MaintenanceType.CONFIG:     "✅ Config appliquée",
    MaintenanceType.SECURITY:   "✅ Patch appliqué",
    MaintenanceType.MIGRATION:  "✅ Migration terminée",
    MaintenanceType.OTHER:      "✅ Maintenance terminée",
}[maintenance_type]
```

- [ ] **Step 3: Pass `maintenance_type` to `DowntimeEmbed.end()` in the restore button handler**

Current line 120 in `restore_button`:
```python
embed = DowntimeEmbed.end(self.service, interaction.user, self.service_type)
```

Replace with:
```python
embed = DowntimeEmbed.end(self.service, interaction.user, self.service_type, self.maintenance_type)
```

- [ ] **Step 4: Verify no syntax errors**

```bash
python -c "from src.utils.views import DowntimeView; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/utils/views.py
git commit -m "feat(views): dynamic restore button label based on maintenance type"
```

---

### Task 3: `downtime.py` — remove dead commands, thread maintenance_type

**Files:**
- Modify: `src/cogs/downtime.py`
- Modify: `src/utils/embeds.py` (remove `start()`)

- [ ] **Step 1: Remove `downtime_slash` command**

Delete the entire `downtime_slash` method (lines 319–403, from `@app_commands.command(name="downtime"...` through the closing `)`of `send_message`).

- [ ] **Step 2: Remove `down_prefix` and `up_prefix` prefix commands**

Delete:
- `down_prefix` method (lines 686–724, from `@commands.command(name="down")` through `await ctx.message.add_reaction("✅")`)
- `up_prefix` method (lines 726–734, from `@commands.command(name="up")` through `await ctx.message.add_reaction("✅")`)

- [ ] **Step 3: Add DOWNTIME choice to `/maintenance` and pass `maintenance_type` to `DowntimeView`**

In `maintenance_slash`, replace the `@app_commands.choices(maintenance_type=[...])` decorator with:

```python
@app_commands.choices(maintenance_type=[
    app_commands.Choice(name="🔧 Interruption", value="downtime"),
    app_commands.Choice(name="⬆️ Mise à jour", value="update"),
    app_commands.Choice(name="💾 Sauvegarde", value="backup"),
    app_commands.Choice(name="⚙️ Config", value="config"),
    app_commands.Choice(name="🔒 Patch sécurité", value="security"),
    app_commands.Choice(name="🚚 Migration", value="migration"),
    app_commands.Choice(name="🛠️ Autre", value="other"),
])
```

This matches the emoji style already used in `/scheduled`'s maintenance_type choices.

Then in the `DowntimeView(...)` call inside `maintenance_slash`, add `maintenance_type=maint_type`:

```python
view = DowntimeView(
    service=service,
    author_id=interaction.user.id,
    duration_str=duration,
    announcement_channel=channel,
    notification_mention=notification_mention,
    service_type=svc_type,
    maintenance_type=maint_type,
)
```

- [ ] **Step 4: Collapse `_trigger_scheduled_downtime` if/else and pass `maintenance_type`**

Current block (lines 170–187):
```python
if maint_type == MaintenanceType.DOWNTIME:
    embed = DowntimeEmbed.start(
        maintenance.service,
        f"[SCHEDULED] {maintenance.reason}",
        maintenance.duration,
        author,
        service_type
    )
else:
    embed = DowntimeEmbed.maintenance(
        maintenance.service,
        f"[SCHEDULED] {maintenance.reason}",
        maintenance.duration,
        author,
        service_type,
        maint_type
    )
```

Replace with:
```python
embed = DowntimeEmbed.maintenance(
    maintenance.service,
    f"[SCHEDULED] {maintenance.reason}",
    maintenance.duration,
    author,
    service_type,
    maint_type,
)
```

Then in the `DowntimeView(...)` call inside `_trigger_scheduled_downtime`, add `maintenance_type=maint_type`:

```python
view = DowntimeView(
    service=maintenance.service,
    author_id=maintenance.author_id,
    duration_str=maintenance.duration,
    announcement_channel=channel,
    notification_mention=notification_mention,
    service_type=service_type,
    maintenance_type=maint_type,
)
```

- [ ] **Step 5: Remove `DowntimeEmbed.start()` from `embeds.py` (now dead)**

Delete the entire `start()` static method from `src/utils/embeds.py` (lines 82–98, from `@staticmethod` through `return embed`).

- [ ] **Step 6: Verify the full bot loads without errors**

```bash
python -c "
import asyncio, discord
from src.bot import create_bot
print('Import OK')
"
```

Expected output: `Import OK`

If that path doesn't work cleanly outside the bot loop, at minimum verify the cog and embeds import:

```bash
python -c "
from src.utils.embeds import DowntimeEmbed, MaintenanceType
from src.utils.views import DowntimeView
from src.cogs.downtime import DowntimeCog
print('All imports OK')
"
```

Expected output: `All imports OK`

- [ ] **Step 7: Commit**

```bash
git add src/cogs/downtime.py src/utils/embeds.py
git commit -m "feat(downtime): merge /downtime into /maintenance, remove prefix commands, dynamic restore embed"
```

---

## Post-Implementation Verification

After all tasks are complete, build and redeploy:

```bash
cd /srv/project/python/FenrirBot && ./build.sh
cd /srv/nebula && ./scripts/start-docker.sh recreate management
```

Test in Discord:
- `/maintenance` — confirm type dropdown shows Interruption first, all 7 types present
- `/maintenance service:plex maintenance_type:downtime reason:test` — restore button should read "✅ Service restauré", restore embed title "Service rétabli · plex"
- `/maintenance service:plex maintenance_type:update reason:test` — restore button "✅ Mise à jour terminée", restore embed "Mise à jour terminée · plex"
- `/downtime` — command should no longer exist
- `/up` — still works, restore embed unchanged
