# 🐺 FenrirBot

> Discord bot for announcing homelab & Docker stack downtime to your friends.

FenrirBot keeps your Discord community informed when services go down, come back up, or need maintenance. It integrates with your monitoring stack (Netdata, Grafana, Prometheus, UptimeKuma) via webhooks and exposes easy-to-use slash commands.

## Documentation

| Page | Description |
|------|-------------|
| [Setup](Setup.md) | Installation and first-time configuration |
| [Commands](Commands.md) | All slash commands and prefix commands |
| [Webhooks](Webhooks.md) | Webhook integrations (Grafana, Netdata, Prometheus, UptimeKuma) |
| [Configuration](Configuration.md) | Full environment variable reference |

## Quick Start

`ash
git clone https://github.com/Spifuth/FenrirBot.git && cd FenrirBot
./scripts/setup.sh
# Edit .env with your DISCORD_TOKEN and ANNOUNCEMENT_CHANNEL_ID
./scripts/run.sh
`

## Architecture

`
Discord ←→ FenrirBot ←→ Webhook Server ←→ Grafana / Netdata / Prometheus / UptimeKuma
`
"@

Push-File "FenrirBot" "docs/Setup.md" "docs: add wiki Setup page" @"
# Setup

## Prerequisites

- Python 3.11+
- A Discord account with a server you manage
- A Discord bot token — get one at the [Developer Portal](https://discord.com/developers/applications)

## 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → name it "Fenrir"
3. Go to **Bot** → click **Add Bot** → copy the **Token**
4. Enable **Message Content Intent** under Privileged Gateway Intents
5. Go to **OAuth2 → URL Generator**: set scopes to ot + pplications.commands, permissions to Send Messages, Embed Links, Mention Everyone
6. Use the generated URL to invite the bot to your server

## 2. Install

`ash
git clone https://github.com/Spifuth/FenrirBot.git
cd FenrirBot
./scripts/setup.sh
`

The setup script creates a virtualenv, installs dependencies, and copies .env.example → .env.

## 3. Configure

Edit .env:

`nv
DISCORD_TOKEN=your_bot_token_here
ANNOUNCEMENT_CHANNEL_ID=123456789012345678
`

See [Configuration](Configuration.md) for all options.

## 4. Run

`ash
./scripts/run.sh
`

## Updating

`ash
git pull && pip install -r requirements.txt
`
"@

Push-File "FenrirBot" "docs/Commands.md" "docs: add wiki Commands page" @"
# Commands

## Slash Commands

| Command | Description |
|---------|-------------|
| /downtime | Announce a service is going offline |
| /backup | Announce a service is back online |
| /scheduled | Announce planned maintenance |
| /status | Send a quick status update |
| /ping | Check bot responsiveness |

### Examples

`
/downtime service:"Minecraft" reason:"Updating mods" duration:"30 minutes"
/backup service:"Minecraft"
/scheduled service:Plex when:"Saturday 2 AM" duration:"1 hour" reason:"DB migration"
/status message:"All systems operational"
`

## Prefix Commands (quick)

| Command | Description |
|---------|-------------|
| !down "<service>" <reason> | Quick downtime announcement |
| !up <service> | Quick back-online announcement |
| !status <message> | Quick status update |

## Netdata Commands

Requires [webhook setup](Webhooks.md#netdata).

| Command | Description |
|---------|-------------|
| /netdata status | Current CPU, RAM, Disk usage |
| /netdata alarms | Active alerts |
| /netdata test | Send a test alert |