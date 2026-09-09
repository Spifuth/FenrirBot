# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

# Run the bot
python run.py

# Build and deploy
./build.sh
cd /srv/nebula && ./scripts/start-docker.sh up management
```

`up management` only recreates containers whose image or config changed, so after a rebuild it touches `fenrirbot` alone. To be explicit — or to restart without rebuilding — target the container directly:

```bash
cd /srv/nebula && ./scripts/start-docker.sh recreate fenrirbot
```

Run the tests with `python3 -m pytest -q` from the repo root.
CI runs them plus `ruff` on every pull request and on pushes to `dev`.

## Architecture

Fenrir is a discord.py bot for announcing service downtime and infrastructure events. It uses the `commands.ext` cog system to organize commands.

### Entry point and initialization flow

`run.py` → `src/bot.py:create_bot()` → `FenrirBot.__init__()` → `setup_hook()` (loads cogs, syncs slash commands, revives open incident views from `data/open_incidents.json`) → `on_ready()`. The webhook server is never constructed — `WEBHOOK_ENABLED` is absent from the deployed compose and defaults to `false`.

**`src/config.py`** — Single `Config` dataclass loaded from `.env` via `python-dotenv`. A module-level `config` singleton is created at import time. All cogs import this singleton directly.

**`src/bot.py`** — `FenrirBot(commands.Bot)`. The `INITIAL_COGS` list controls which cogs load. Add new cog module paths here to register them.

### Cogs (`src/cogs/`)

Each cog is a `commands.Cog` subclass with an `async def setup(bot)` function. Cogs provide both slash commands (`@app_commands.command`) and prefix commands (`@commands.command`).

- **`downtime.py`** — Core cog. `/maintenance`, `/up`, `/scheduled`, `/scheduled-list`, `/scheduled-cancel`. Background `tasks.loop` checks every 30s for due scheduled maintenances. Times are parsed as **Europe/Paris** via `parse_local_datetime` and stored as UTC. Persists to `data/scheduled_maintenances.json`; open incidents to `data/open_incidents.json`.
- **`status.py`** — `/status`, `/ping`, `!status`.
- **`docker.py`** — `/containers`, `/stacks`, `/refresh`. Refreshes the container cache every 5 minutes off the event loop.
- **`dashboard.py`** — `/dashboard` (Docker status overview).
- **`reports.py`** — `/rapport`, VictoriaMetrics-backed.
- **`alerts.py`** — `/alerts`, Grafana Alertmanager-backed.
- **`server_config.py`** — `/server-config validate|diff|apply|export`, `webhooks reveal`. Declarative guild reconciliation from `specs/server-spec.yaml`.

**Permissions:** every command except `/ping` is gated by `admin_only()` from `src/utils/permissions.py`, which applies both `default_permissions` and a runtime `has_permissions` check.

### Utils (`src/utils/`)

- **`embeds.py`** — `DowntimeEmbed` and `DashboardEmbed` builders. Defines `ServiceType` and `MaintenanceType` enums with icons, colors, labels, and verbs. Uses random GIFs from Giphy and Twemoji CDN thumbnails.
- **`views.py`** — `DowntimeView(ui.View)`: the interactive message with "Service Restored" and "Cancel" buttons. Parses duration strings, runs a background timer, and manages incident thread lifecycle.
- **`personality.py`** — `FenrirPersonality` with mood-based greetings/messages that change based on time of day (SLEEPY 0-6h, MORNING 6-10h, ENERGETIC 10-14h, CHILL 14-18h, EVENING 18-22h, NIGHT 22-24h). Messages are mostly in French.
- **`webhook_server.py`** — **Dead code.** The aiohttp server and its Traefik router were removed on 2026-08-30; `WEBHOOK_ENABLED` is not in the compose, so `src/bot.py` never constructs it. Kept only for reference.
- **`incidents.py`** — `IncidentStore`: persists open incident announcements so buttons survive a restart.
- **`permissions.py`** — `admin_only()` decorator.
- **`docker.py`** — Docker SDK wrapper with a cache layer. `docker_manager` singleton.
- **`helpers.py`** — Shared utilities used across all cogs: channel/mention resolution, `create_progress_bar()`, `get_metric_emoji()`, `get_status_color()`, `format_duration()`, Discord timestamp formatters, standardized embed builders, threshold constants (cpu/ram/disk/etc.), and Paris timezone.

### Persistent data (`data/`)

JSON files managed directly by cogs:
- `data/scheduled_maintenances.json` — Pending scheduled maintenances (survives bot restarts)
- `data/containers.json` — Docker container cache
- `data/open_incidents.json` — Open incident announcements (`IncidentStore`), so buttons survive a restart
- `data/server_config_state.json` — `/server-config` webhook and reaction-binding state

### Adding a new cog

1. Create `src/cogs/mycommands.py` with a `commands.Cog` subclass and `async def setup(bot)`.
2. Add the module path to `INITIAL_COGS` in `src/bot.py`.

### Language convention

Discord-facing messages (command descriptions, announcements, responses) are primarily in **French**. Python code, comments, and docstrings are in English.

## Key `.env` variables

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required. Bot token. |
| `ANNOUNCEMENT_CHANNEL_ID` | Channel for downtime announcements. |
| `NOTIFICATION_ROLE_ID` | Role to `@mention` (falls back to `@here` if 0). |
| `VICTORIAMETRICS_URL` | VictoriaMetrics base URL (e.g. `http://victoriametrics:8428`). |
| `GRAFANA_URL` | Grafana base URL (e.g. `http://grafana:3000`). |
| `GRAFANA_API_KEY` | Grafana service account token (Viewer role). |
| `REPORTS_CHANNEL_ID` | **Dead config** — read by `Config` but no cog uses it. |

The `WEBHOOK_*` variables are not set in the deployed compose; the webhook server is dead code.
