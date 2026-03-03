# Commands

## Slash Commands

| Command | Description |
|---------|-------------|
| `/downtime` | Announce a service is going offline |
| `/backup` | Announce a service is back online |
| `/scheduled` | Announce planned maintenance |
| `/status` | Send a quick status update |
| `/ping` | Check bot responsiveness |

### Examples

```
/downtime service:"Minecraft" reason:"Updating mods" duration:"30 minutes"
/backup service:"Minecraft"
/scheduled service:Plex when:"Saturday 2 AM" duration:"1 hour" reason:"DB migration"
/status message:"All systems operational"
```

## Prefix Commands (quick)

| Command | Description |
|---------|-------------|
| `!down "<service>" <reason>` | Quick downtime announcement |
| `!up <service>` | Quick back-online announcement |
| `!status <message>` | Quick status update |

## Netdata Commands

Requires [webhook setup](Webhooks.md#netdata).

| Command | Description |
|---------|-------------|
| `/netdata status` | Current CPU, RAM, Disk usage |
| `/netdata alarms` | Active alerts |
| `/netdata test` | Send a test alert |
