"""Fenrir Bot - Main bot class and initialization"""

import discord
from discord.ext import commands

from .config import config
from .utils.uptimekuma import init_uptimekuma


class FenrirBot(commands.Bot):
    """Main bot class for Fenrir"""
    
    # List of cogs to load on startup
    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
    ]
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix=config.command_prefix if config else "!",
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )
        
        # Initialize UptimeKuma client if configured
        if config and config.uptimekuma_url:
            init_uptimekuma(config.uptimekuma_url, config.uptimekuma_api_key)
            print(f"  ✅ UptimeKuma: {config.uptimekuma_url}")
    
    async def setup_hook(self):
        """Called when the bot is starting up - load cogs here"""
        for cog in self.INITIAL_COGS:
            try:
                await self.load_extension(cog)
                print(f"  ✅ Loaded: {cog}")
            except Exception as e:
                print(f"  ❌ Failed to load {cog}: {e}")
        
        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            print(f"  ✅ Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  ❌ Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when the bot is fully connected and ready"""
        print(f"\n🐺 Fenrir is online!")
        print(f"   User: {self.user}")
        print(f"   Guilds: {len(self.guilds)}")
        print(f"   Prefix: {self.command_prefix}")
        if config and config.announcement_channel_id:
            print(f"   Announcement Channel: {config.announcement_channel_id}")
        print()


def create_bot() -> FenrirBot:
    """Factory function to create a configured bot instance"""
    return FenrirBot()
