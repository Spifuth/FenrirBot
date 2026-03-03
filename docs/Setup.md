# Setup

## Prerequisites

- Python 3.11+
- A Discord account with a server you manage
- A Discord bot token from the [Developer Portal](https://discord.com/developers/applications)

## 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and name it "Fenrir"
3. Go to **Bot** tab, click **Add Bot**, copy the **Token**
4. Enable **Message Content Intent** under Privileged Gateway Intents
5. **OAuth2 → URL Generator**: scopes = `bot` + `applications.commands`, permissions = `Send Messages`, `Embed Links`, `Mention Everyone`
6. Use the generated URL to invite the bot to your server

## 2. Install

```bash
git clone https://github.com/Spifuth/FenrirBot.git
cd FenrirBot
./scripts/setup.sh
```

The setup script creates a virtualenv, installs dependencies, and copies `.env.example` → `.env`.

## 3. Configure

Edit `.env`:

```env
DISCORD_TOKEN=your_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678
```

See [Configuration](Configuration.md) for all options.

## 4. Run

```bash
./scripts/run.sh
```

Or manually:
```bash
source venv/bin/activate
python run.py
```

## Updating

```bash
git pull && pip install -r requirements.txt
```
