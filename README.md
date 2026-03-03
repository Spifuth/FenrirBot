# 🐺 Fenrir Bot

Discord bot for announcing server/Docker stack downtime to your friends.

## Features

- **`/downtime`** - Announce a service is going offline (with reason & estimated duration)
- **`/backup`** - Announce a service is back online
- **`/scheduled`** - Announce planned maintenance windows
- **`/status`** - Send quick status updates
- **`!down`** / **`!up`** - Quick prefix commands for fast announcements

## Project Structure

```
FenrirBot/
├── run.py                 # Entry point
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
├── scripts/
│   ├── setup.sh           # Automated setup (venv + deps)
│   └── run.sh             # Run with venv
└── src/
    ├── __init__.py
    ├── bot.py             # Bot class & initialization
    ├── config.py          # Configuration management
    ├── cogs/              # Command modules
    │   ├── __init__.py
    │   ├── downtime.py    # Downtime commands
    │   └── status.py      # Status commands
    └── utils/
        ├── __init__.py
        └── embeds.py      # Embed builders
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

### 2. Quick Setup (Recommended)

```bash
cd /srv/project/python/FenrirBot
./scripts/setup.sh
```

This will:
- Create a Python virtual environment (`venv/`)
- Install all dependencies
- Create `.env` from template

Then edit `.env` with your values:
```
DISCORD_TOKEN=your_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678
```

> 💡 To get a channel ID: Enable Developer Mode in Discord settings, then right-click the channel → Copy ID

### 3. Run the Bot

```bash
./scripts/run.sh
```

Or manually:
```bash
source venv/bin/activate
python run.py
```

## Usage Examples

### Slash Commands (recommended)
```
/downtime service:Minecraft Server reason:Updating mods duration:30 minutes
/backup service:Minecraft Server
/scheduled service:Plex when:Saturday 2 AM duration:1 hour reason:Database migration
/status message:All systems operational
/ping
```

### Quick Prefix Commands
```
!down "Minecraft Server" Updating to 1.21
!up Minecraft Server
!status All systems operational
```

## 🖥️ Netdata Integration (System Monitoring)

Fenrir can receive alerts from Netdata for CPU, RAM, Disk, Network, and Temperature monitoring.

### Setup Netdata Webhooks

1. **Enable webhooks in your `.env`:**
```env
WEBHOOK_ENABLED=true
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8085
WEBHOOK_SECRET=your_secret_token  # Optional but recommended
NETDATA_URL=http://localhost:19999  # For /netdata commands
```

2. **Configure Netdata to send alerts to Fenrir:**
```bash
# On your Netdata server, run:
./scripts/setup-netdata-webhook.sh http://YOUR_BOT_IP:8085 your_secret_token
```

3. **Or configure manually** - Edit `/etc/netdata/health_alarm_notify.conf`:
```bash
SEND_CUSTOM="YES"
DEFAULT_RECIPIENT_CUSTOM="http://YOUR_BOT_IP:8080/webhook/netdata"
```

### Netdata Slash Commands
```
/netdata status   # View current CPU, RAM, Disk usage
/netdata alarms   # View active alerts
/netdata test     # Send a test alert
```

### Supported Alert Types
- 🖥️ **CPU** - High CPU utilization alerts
- 🧠 **RAM** - Memory usage warnings
- 💾 **Disk** - Disk space alerts
- 🌐 **Network** - Bandwidth and traffic alerts
- 🌡️ **Temperature** - CPU/System temperature warnings
- 📊 **Load** - System load averages

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