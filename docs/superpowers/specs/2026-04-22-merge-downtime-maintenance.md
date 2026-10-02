# Spec: Merge `/downtime` into `/maintenance`

**Date:** 2026-04-22  
**Status:** Approved

## Context

`/downtime` and `/maintenance` share identical flow (announce embed → incident thread → restore button). The only difference is `/downtime` locks `MaintenanceType` to DOWNTIME (Interruption) while `/maintenance` lets the user choose a type. Since DOWNTIME is just another maintenance type, `/downtime` is redundant.

## Goal

Remove `/downtime` (and prefix commands `!down`, `!up`). `/maintenance` becomes the single announce command, with `maintenance_type` as the first required parameter — no default, always selected explicitly.

## Command: `/maintenance`

**Parameters (in order):**

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `service` | str | yes | — | autocomplete from Docker containers + stacks |
| `maintenance_type` | choice | yes | — | no default, must be selected |
| `reason` | str | yes | — | |
| `duration` | str | no | `"Inconnue"` | |
| `service_type` | choice | no | auto-detected | container / stack / other |
| `mention` | bool | no | `True` | |

**`maintenance_type` choices (all 7):**

| Value | Display label |
|---|---|
| `downtime` | Interruption |
| `update` | Mise à jour |
| `backup` | Sauvegarde |
| `config` | Config |
| `security` | Patch sécurité |
| `migration` | Migration |
| `other` | Autre |

## Commands Removed

- `/downtime` slash command
- `!down` prefix command
- `!up` prefix command

**Kept as-is:**
- `/up` slash command (manual restore, no changes)
- `/scheduled`, `/scheduled-list`, `/scheduled-cancel` (no changes — already use `MaintenanceType` including DOWNTIME)

## `DowntimeView` — Dynamic Restore Button

Add `maintenance_type: MaintenanceType` to `__init__`. Button label is set at construction time using a dict lookup:

```python
{
    MaintenanceType.DOWNTIME:   "Service restauré",
    MaintenanceType.UPDATE:     "Mise à jour terminée",
    MaintenanceType.BACKUP:     "Sauvegarde terminée",
    MaintenanceType.CONFIG:     "Config appliquée",
    MaintenanceType.SECURITY:   "Patch appliqué",
    MaintenanceType.MIGRATION:  "Migration terminée",
    MaintenanceType.OTHER:      "Maintenance terminée",
}[maintenance_type]
```

All callers of `DowntimeView` must pass `maintenance_type`. Callers:
- `/maintenance` slash command (direct)
- `_trigger_scheduled_downtime()` (already has `maint_type` in scope)

## `DowntimeEmbed.end()` — Type-Aware Restore Embed

Add `maintenance_type: MaintenanceType | None = None` parameter.

- When `None` or `MaintenanceType.DOWNTIME`: existing behavior ("Service restauré — {service}")
- When another type: title becomes `"{maint_type.label} terminée — {service}"` (e.g. "Mise à jour terminée — plex")

Callers of `DowntimeEmbed.end()`:
- `/up` slash command — passes `None` (no change)
- `DowntimeView` restore button handler — passes the stored `maintenance_type`
- `!up` prefix command — removed

## Files Changed

| File | Change |
|---|---|
| `src/cogs/downtime.py` | Remove `downtime_slash`, `down_prefix`, `up_prefix`; reorder `/maintenance` params; pass `maintenance_type` to `DowntimeView` |
| `src/utils/views.py` | Add `maintenance_type` param; dynamic button label; pass type to `DowntimeEmbed.end()` |
| `src/utils/embeds.py` | `end()` accepts `maintenance_type: MaintenanceType \| None = None`; adapt title for non-DOWNTIME types |

## Out of Scope

- No changes to `/up`, `/scheduled`, `/scheduled-list`, `/scheduled-cancel`
- No changes to embed visual style (already redesigned)
- No changes to thread creation logic (already correct per type in `/maintenance`)
