# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (first time)
./scripts/setup.sh           # Creates venv and installs dependencies

# Run the bot
source venv/bin/activate
python run.py

# Or via script
./scripts/run.sh

# Install/update dependencies
pip install -r requirements.txt
```

Run the tests with `pytest -q` from the repo root (13 tests under `tests/`).
CI runs them on every pull request and on pushes to `dev`.

## Architecture

Fenrir is a discord.py bot for announcing service downtime and infrastructure events. It uses the `commands.ext` cog system to organize commands.

### Entry point and initialization flow

`run.py` → `src/bot.py:create_bot()` → `FenrirBot.__init__()` → `setup_hook()` (loads cogs, syncs slash commands) → `on_ready()` (starts webhook server if enabled).

**`src/config.py`** — Single `Config` dataclass loaded from `.env` via `python-dotenv`. A module-level `config` singleton is created at import time. All cogs import this singleton directly.

**`src/bot.py`** — `FenrirBot(commands.Bot)`. The `INITIAL_COGS` list controls which cogs load. Add new cog module paths here to register them.

### Cogs (`src/cogs/`)

Each cog is a `commands.Cog` subclass with an `async def setup(bot)` function. Cogs provide both slash commands (`@app_commands.command`) and prefix commands (`@commands.command`).

- **`downtime.py`** — Core cog. `/downtime`, `/up`, `/maintenance`, `/scheduled`, `/scheduled-list`, `/scheduled-cancel`, `!down`, `!up`. Manages a background `tasks.loop` that checks every 30s for scheduled maintenances and auto-triggers them. Persists scheduled maintenances to `data/scheduled_maintenances.json`.
- **`status.py`** — `/status`, `/ping`. Status updates.
- **`docker.py`** — `/containers`, `/stacks`, `/refresh`. Refreshes Docker container list every 5 minutes. Also exposes autocomplete functions used by the downtime cog.
- **`dashboard.py`** — Dashboard display commands (Docker status overview).

### Utils (`src/utils/`)

- **`embeds.py`** — `DowntimeEmbed` and `DashboardEmbed` builders. Defines `ServiceType` and `MaintenanceType` enums with icons, colors, labels, and verbs. Uses random GIFs from Giphy and Twemoji CDN thumbnails.
- **`views.py`** — `DowntimeView(ui.View)`: the interactive message with "Service Restored" and "Cancel" buttons. Parses duration strings, runs a background timer, and manages incident thread lifecycle.
- **`personality.py`** — `FenrirPersonality` with mood-based greetings/messages that change based on time of day (SLEEPY 0-6h, MORNING 6-10h, ENERGETIC 10-14h, CHILL 14-18h, EVENING 18-22h, NIGHT 22-24h). Messages are mostly in French.
- **`webhook_server.py`** — `WebhookServer` using aiohttp. Routes: `POST /webhook/generic`, `POST /webhook/prometheus`, `POST /webhook/grafana`, `GET /health`, `GET /metrics`. Started inside `on_ready()` if `WEBHOOK_ENABLED=true`.
- **`docker.py`** — Docker SDK wrapper with a cache layer. `docker_manager` singleton.
- **`helpers.py`** — Shared utilities used across all cogs: channel/mention resolution, `create_progress_bar()`, `get_metric_emoji()`, `get_status_color()`, `format_duration()`, Discord timestamp formatters, standardized embed builders, threshold constants (cpu/ram/disk/etc.), and Paris timezone.

### Persistent data (`data/`)

JSON files managed directly by cogs:
- `data/scheduled_maintenances.json` — Pending scheduled maintenances (survives bot restarts)
- `data/containers.json` — Docker container cache

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
| `WEBHOOK_ENABLED` | Start aiohttp webhook server (default: `false`). |
| `WEBHOOK_PORT` | Webhook server port (default: `8085`). |
| `WEBHOOK_SECRET` | Bearer token for webhook auth (optional). |
| `VICTORIAMETRICS_URL` | VictoriaMetrics base URL (e.g. `http://victoriametrics:8428`). |
| `REPORTS_CHANNEL_ID` | Channel for auto-posted reports (optional). |
| `GRAFANA_URL` | Grafana base URL (e.g. `http://grafana:3000`). |
| `GRAFANA_API_KEY` | Grafana service account token (Viewer role). |
