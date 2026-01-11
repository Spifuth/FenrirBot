"""Downtime announcement commands"""

import discord
from discord import app_commands
from discord.ext import commands

from ..config import config
from ..utils.embeds import DowntimeEmbed, ServiceType
from ..utils.docker import docker_manager
from ..utils.views import DowntimeView


class DowntimeCog(commands.Cog, name="Downtime"):
    """Commands for announcing service downtime and restoration"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._containers_cache: set[str] = set()
        self._stacks_cache: set[str] = set()
    
    def _refresh_service_cache(self):
        """Refresh the cached lists of containers and stacks"""
        self._containers_cache = set(docker_manager.get_container_names(include_stopped=True))
        self._stacks_cache = set(docker_manager.get_stacks())
    
    def _get_service_type(self, service_name: str) -> ServiceType:
        """Determine if a service is a container, stack, or other"""
        # Refresh cache if empty
        if not self._containers_cache and not self._stacks_cache:
            self._refresh_service_cache()
        
        if service_name in self._containers_cache:
            return ServiceType.CONTAINER
        elif service_name in self._stacks_cache:
            return ServiceType.STACK
        else:
            return ServiceType.OTHER
    
    async def service_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for service names from Docker containers + stacks"""
        # Refresh cache
        self._refresh_service_cache()
        
        choices = []
        
        # Add containers with 🐳 prefix in display
        for name in self._containers_cache:
            if not current or current.lower() in name.lower():
                choices.append(
                    app_commands.Choice(name=f"🐳 {name}", value=name)
                )
        
        # Add stacks with 📚 prefix in display  
        for name in self._stacks_cache:
            if not current or current.lower() in name.lower():
                # Don't add if already in containers (same name)
                if name not in self._containers_cache:
                    choices.append(
                        app_commands.Choice(name=f"📚 {name}", value=name)
                    )
        
        # Sort by name and limit to 25
        choices.sort(key=lambda c: c.name)
        return choices[:25]
    
    def _get_announcement_channel(self, fallback: discord.TextChannel) -> discord.TextChannel:
        """Get the configured announcement channel or fall back to current channel"""
        if config and config.announcement_channel_id:
            channel = self.bot.get_channel(config.announcement_channel_id)
            if channel:
                return channel
        return fallback
    
    def _get_notification_mention(self) -> str:
        """Get the role mention string or fall back to @here"""
        if config and config.notification_role_id:
            return f"<@&{config.notification_role_id}>"
        return "@here"

    # ========== Slash Commands ==========
    
    @app_commands.command(name="downtime", description="Announce that a service is going down for maintenance")
    @app_commands.describe(
        service="Name of the service/container going down (e.g., 'Minecraft Server', 'Plex')",
        reason="Reason for the downtime",
        duration="Estimated duration (e.g., '30 minutes', '2 hours')"
    )
    @app_commands.autocomplete(service=service_autocomplete)
    async def downtime_slash(
        self, 
        interaction: discord.Interaction, 
        service: str, 
        reason: str, 
        duration: str = "Unknown"
    ):
        """Announce service downtime via slash command"""
        channel = self._get_announcement_channel(interaction.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.start(service, reason, duration, interaction.user, service_type)
        
        # Create interactive view with restore button
        view = DowntimeView(
            service=service,
            author_id=interaction.user.id,
            duration_str=duration,
            announcement_channel=channel,
            notification_mention=self._get_notification_mention(),
            service_type=service_type
        )
        
        # Send announcement with buttons
        msg = await channel.send(
            content=self._get_notification_mention(), 
            embed=embed,
            view=view
        )
        view.message = msg
        
        # Start timer if duration was parsed
        await view.start_timer()
        
        await interaction.response.send_message(
            f"✅ Downtime announcement sent for **{service}** ({service_type.label})\n"
            f"💡 Click the button on the announcement to mark as restored.",
            ephemeral=True
        )

    @app_commands.command(name="backup", description="Announce service restored / back online")
    @app_commands.describe(service="Name of the service that is back online")
    @app_commands.autocomplete(service=service_autocomplete)
    async def backup_slash(self, interaction: discord.Interaction, service: str):
        """Announce service restoration via slash command"""
        channel = self._get_announcement_channel(interaction.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.end(service, interaction.user, service_type)
        
        await channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Service restored announcement sent for **{service}** ({service_type.label})", 
            ephemeral=True
        )

    @app_commands.command(name="scheduled", description="Announce a scheduled maintenance window")
    @app_commands.describe(
        service="Name of the service",
        when="When the maintenance will occur (e.g., 'Tomorrow 10 PM', 'Saturday 2 AM')",
        duration="Expected duration",
        reason="Reason for maintenance"
    )
    @app_commands.autocomplete(service=service_autocomplete)
    async def scheduled_slash(
        self, 
        interaction: discord.Interaction, 
        service: str, 
        when: str, 
        duration: str, 
        reason: str
    ):
        """Announce scheduled maintenance via slash command"""
        channel = self._get_announcement_channel(interaction.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.scheduled(service, when, duration, reason, interaction.user, service_type)
        
        await channel.send(content=self._get_notification_mention(), embed=embed)
        await interaction.response.send_message(
            f"✅ Scheduled maintenance announcement sent for **{service}** ({service_type.label})", 
            ephemeral=True
        )

    # ========== Prefix Commands ==========
    
    @commands.command(name="down")
    async def down_prefix(self, ctx: commands.Context, service: str, *, reason: str = "Maintenance"):
        """Quick downtime announcement: !down "Service Name" Reason here"""
        channel = self._get_announcement_channel(ctx.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.start(service, reason, "Unknown", ctx.author, service_type)
        
        # Create interactive view with restore button
        view = DowntimeView(
            service=service,
            author_id=ctx.author.id,
            duration_str="Unknown",
            announcement_channel=channel,
            notification_mention=self._get_notification_mention(),
            service_type=service_type
        )
        
        msg = await channel.send(
            content=self._get_notification_mention(), 
            embed=embed,
            view=view
        )
        view.message = msg
        
        await ctx.message.add_reaction("✅")

    @commands.command(name="up")
    async def up_prefix(self, ctx: commands.Context, *, service: str):
        """Quick service restored: !up Service Name"""
        channel = self._get_announcement_channel(ctx.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.end(service, ctx.author, service_type)
        
        await channel.send(embed=embed)
        await ctx.message.add_reaction("✅")


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DowntimeCog(bot))
