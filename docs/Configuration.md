# Configuration

All settings live in `.env`. Copy `.env.example` to get started.

## Required

| Variable | Description |
|----------|-------------|
| `DISCORD_TOKEN` | Your Discord bot token |
| `ANNOUNCEMENT_CHANNEL_ID` | Channel ID for downtime announcements |

## Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `NOTIFICATION_ROLE_ID` | `0` | Role to ping on alerts (0 = disabled) |
| `COMMAND_PREFIX` | `!` | Prefix for text commands |
| `REPORTS_CHANNEL_ID` | `0` | Channel for periodic reports (0 = disabled) |

## Uptime Kuma

| Variable | Default | Description |
|----------|---------|-------------|
| `UPTIMEKUMA_URL` | — | UptimeKuma instance URL |
| `UPTIMEKUMA_API_KEY` | — | API key for status queries |
| `UPTIMEKUMA_STATUS_PAGE` | `default` | Status page slug |
| `UPTIMEKUMA_USERNAME` | — | Username for pause/resume monitors |
| `UPTIMEKUMA_PASSWORD` | — | Password for pause/resume monitors |
| `UPTIMEKUMA_AUTO_PAUSE` | `true` | Auto-pause monitors during maintenance |

## Webhook Server

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_ENABLED` | `false` | Enable the alert receiver server |
| `WEBHOOK_HOST` | `0.0.0.0` | Bind address |
| `WEBHOOK_PORT` | `8085` | Port |
| `WEBHOOK_SECRET` | — | Shared secret for request validation |

## Netdata

| Variable | Description |
|----------|-------------|
| `NETDATA_URL` | Netdata instance URL |
| `NETDATA_API_KEY` | Netdata API key |

> **Tip:** Enable Developer Mode in Discord (Settings → Advanced) then right-click any channel/role → **Copy ID**.
