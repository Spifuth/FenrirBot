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