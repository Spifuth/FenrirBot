"""Fenrir Bot - Main bot class and initialization"""

import discord
from discord.ext import commands
from typing import Optional

from .config import config
from .utils.webhook_server import WebhookServer
from .utils.incidents import incident_store
from .utils.views import DowntimeView


class FenrirBot(commands.Bot):
    """Main bot class for Fenrir"""

    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
        "src.cogs.reports",
        "src.cogs.alerts",
        "src.cogs.server_config",
    ]

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.reactions = True

        super().__init__(
            command_prefix=config.command_prefix if config else "!",
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )

        self.webhook_server: Optional[WebhookServer] = None

        if config and config.webhook_enabled:
            self.webhook_server = WebhookServer(
                bot=self,
                host=config.webhook_host,
                port=config.webhook_port,
                secret_token=config.webhook_secret or None
            )

    async def setup_hook(self):
        """Called when the bot is starting up - load cogs here"""
        for cog in self.INITIAL_COGS:
            try:
                await self.load_extension(cog)
                print(f"  ✅ Loaded: {cog}")
            except Exception as e:
                print(f"  ❌ Failed to load {cog}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"  ✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  ❌ Failed to sync commands: {e}")

        # Revive the buttons on any incident that was still open at shutdown.
        # load() already tolerates a corrupt/malformed store file, but an
        # unforeseen failure here must still degrade to "no incidents
        # revived" rather than aborting startup entirely.
        try:
            records = list(incident_store.load().values())
        except Exception as e:
            print(f"  ⚠️ Could not load incident store: {e!r}")
            records = []

        revived = 0
        for record in records:
            try:
                self.add_view(DowntimeView.from_record(record, incident_store),
                              message_id=record.message_id)
                revived += 1
            except Exception as e:
                print(f"  ⚠️ Could not revive incident {record.message_id}: {e!r}")
        if revived:
            print(f"  ✅ Revived {revived} open incident view(s)")

    async def on_ready(self):
        """Called when the bot is fully connected and ready"""
        print(f"\n🐺 Fenrir is online!")
        print(f"   User: {self.user}")
        print(f"   Guilds: {len(self.guilds)}")
        print(f"   Prefix: {self.command_prefix}")
        if config and config.announcement_channel_id:
            print(f"   Announcement Channel: {config.announcement_channel_id}")

        if self.webhook_server and config:
            self.webhook_server.set_channel(config.announcement_channel_id)
            if config.notification_role_id:
                self.webhook_server.set_mention(f"<@&{config.notification_role_id}>")
            await self.webhook_server.start()
            print(f"   Webhook Server: http://{config.webhook_host}:{config.webhook_port}")
        print()

    async def close(self):
        """Cleanup when bot is shutting down"""
        if self.webhook_server:
            await self.webhook_server.stop()
        await super().close()


def create_bot() -> FenrirBot:
    """Factory function to create a configured bot instance"""
    return FenrirBot()
