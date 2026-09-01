# 🐺 Fenrir Bot

Discord bot for announcing server/Docker stack downtime to your friends.

## Features

All commands are **administrator-only** except `/ping`.

**Announcements**
- **`/maintenance`** — announce a maintenance (update, backup, config, security patch, migration) with an interactive "terminé" button and an incident thread
- **`/up`** — announce a service is back
- **`/scheduled`** — schedule a future maintenance; it fires automatically (times are read as **Europe/Paris**)
- **`/scheduled-list`** / **`/scheduled-cancel`** — manage pending schedules
- **`/status`**, **`!status`** — quick status update

**Homelab readouts**
- **`/containers`**, **`/stacks`**, **`/refresh`** — Docker inventory via `socket-proxy`
- **`/dashboard`** — container status overview
- **`/rapport`** — CPU/RAM/network report from VictoriaMetrics
- **`/alerts`** — active Grafana alerts
- **`/ping`** — latency check (open to everyone)

**Server configuration**
- **`/server-config validate|diff|apply|export`** and **`/server-config webhooks reveal`** — declarative guild reconciliation from `specs/server-spec.yaml`. See [`src/server_config/README.md`](src/server_config/README.md).

## Project Structure

```
FenrirBot/
├── run.py                 # Entry point
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
└── src/
    ├── __init__.py
    ├── bot.py             # Bot class & initialization
    ├── config.py          # Configuration management
    ├── cogs/              # Command modules
    │   ├── downtime.py    # /maintenance, /up, /scheduled*
    │   ├── status.py      # /status, /ping
    │   ├── docker.py      # /containers, /stacks, /refresh
    │   ├── dashboard.py   # /dashboard
    │   ├── reports.py     # /rapport (VictoriaMetrics)
    │   ├── alerts.py      # /alerts (Grafana)
    │   └── server_config.py  # /server-config *
    ├── server_config/     # Declarative guild reconciliation
    └── utils/
        ├── embeds.py      # Embed builders
        ├── views.py       # Interactive buttons (persistent)
        ├── incidents.py   # Open-incident persistence
        ├── permissions.py # admin_only() gate
        ├── docker.py      # Docker SDK wrapper + cache
        ├── grafana.py     # Grafana REST client
        ├── victoriametrics.py
        ├── helpers.py     # Shared helpers, PARIS_TZ
        └── personality.py # Mood by time of day
```

## Setup

### 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" → Name it "Fenrir"
3. Go to **Bot** tab → Click "Add Bot"
4. Copy the **Token** (you'll need this)
5. Enable **Message Content Intent** under Privileged Gateway Intents
6. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Mention Everyone`
7. Use the generated URL to invite the bot to your server

### 2. Setup

```bash
cd /srv/project/python/FenrirBot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Then edit `.env` with your values:
```
DISCORD_TOKEN=your_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678
```

> 💡 To get a channel ID: Enable Developer Mode in Discord settings, then right-click the channel → Copy ID

### 3. Run the Bot

```bash
source venv/bin/activate
python run.py
```

### 4. Run the tests

```bash
python3 -m pytest -q
```

### 5. Deploy

```bash
./build.sh                                        # builds fenrirbot:latest
cd /srv/nebula && ./scripts/start-docker.sh up management
```

## Usage Examples

```
/maintenance service:traefik maintenance_type:security reason:Patch CVE duration:30 minutes
/up service:traefik
/scheduled service:plex when:2026-09-05 22:00 duration:1 heure reason:Migration DB
/status message:Tout est opérationnel
/rapport periode:weekly
/ping
```

> `when:` is read as **Europe/Paris** wall-clock time.

## Adding New Cogs

Create a new file in `src/cogs/`, e.g. `src/cogs/mycommands.py`:

```python
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command()
    async def hello(self, ctx):
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

Then add it to `INITIAL_COGS` in `src/bot.py`:
```python
INITIAL_COGS = [
    "src.cogs.downtime",
    "src.cogs.status",
    "src.cogs.mycommands",  # Add here
]
```

## License

MIT