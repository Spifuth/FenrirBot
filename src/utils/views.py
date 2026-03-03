"""Interactive views (buttons, modals) for Fenrir Bot"""

import discord
from discord import ui
from datetime import datetime, timedelta
import asyncio
import re
from typing import Optional

from .embeds import DowntimeEmbed, ServiceType
from . import uptimekuma as uptimekuma_module


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse a duration string like '30 minutes', '2 hours', '1h30m' into timedelta"""
    duration_str = duration_str.lower().strip()
    
    # Try patterns like "30 minutes", "2 hours", "1 hour 30 minutes"
    total_seconds = 0
    
    # Hours
    hours_match = re.search(r'(\d+)\s*(?:hours?|h)', duration_str)
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600
    
    # Minutes
    mins_match = re.search(r'(\d+)\s*(?:minutes?|mins?|m(?!o))', duration_str)
    if mins_match:
        total_seconds += int(mins_match.group(1)) * 60
    
    # Seconds
    secs_match = re.search(r'(\d+)\s*(?:seconds?|secs?|s)', duration_str)
    if secs_match:
        total_seconds += int(secs_match.group(1))
    
    if total_seconds > 0:
        return timedelta(seconds=total_seconds)
    
    return None


class DowntimeView(ui.View):
    """Interactive view for downtime announcements with restore button"""
    
    def __init__(
        self, 
        service: str, 
        author_id: int, 
        duration_str: str = "Unknown",
        announcement_channel: Optional[discord.abc.Messageable] = None,
        notification_mention: Optional[str] = "@here",
        service_type: ServiceType = ServiceType.OTHER,
        uptimekuma_paused: bool = False,
        uptimekuma_monitor_id: Optional[int] = None
    ):
        # Timeout after 24 hours
        super().__init__(timeout=86400)
        self.service = service
        self.author_id = author_id
        self.duration_str = duration_str
        self.announcement_channel = announcement_channel
        self.notification_mention = notification_mention
        self.service_type = service_type
        self.resolved = False
        self.message: Optional[discord.Message] = None
        self.timer_task: Optional[asyncio.Task] = None
        self.incident_thread: Optional[discord.Thread] = None
        
        # UptimeKuma integration
        self.uptimekuma_paused = uptimekuma_paused
        self.uptimekuma_monitor_id = uptimekuma_monitor_id
        
        # Parse duration for timer
        self.duration = parse_duration(duration_str)
        self.start_time = datetime.now()
    
    async def start_timer(self):
        """Start a background timer that reminds when duration is up"""
        if not self.duration:
            return
        
        async def timer_callback():
            try:
                await asyncio.sleep(self.duration.total_seconds())
                
                if not self.resolved and self.message:
                    # Send a reminder
                    await self.message.reply(
                        f"⏰ **Reminder:** The estimated downtime for **{self.service}** "
                        f"({self.duration_str}) has elapsed!\n"
                        f"<@{self.author_id}> - Click the button below to mark as restored, "
                        f"or ignore if still in progress."
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Timer error: {e}")
        
        self.timer_task = asyncio.create_task(timer_callback())
    
    @ui.button(label="✅ Service Restored", style=discord.ButtonStyle.green)
    async def restore_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to mark service as restored"""
        # Only the original author can click
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can mark it as restored.",
                ephemeral=True
            )
            return
        
        self.resolved = True
        
        # Cancel timer if running
        if self.timer_task:
            self.timer_task.cancel()
        
        # Resume UptimeKuma monitor if it was paused
        uptimekuma_resumed = False
        if self.uptimekuma_paused and uptimekuma_module.uptimekuma_auth_client:
            try:
                if self.uptimekuma_monitor_id:
                    success = await uptimekuma_module.uptimekuma_auth_client.resume_monitor(self.uptimekuma_monitor_id)
                else:
                    success, _ = await uptimekuma_module.uptimekuma_auth_client.resume_monitor_by_name(self.service)
                uptimekuma_resumed = success
            except Exception as e:
                print(f"[UptimeKuma] Error resuming monitor on restore: {e}")
        
        # Calculate actual downtime
        actual_duration = datetime.now() - self.start_time
        hours, remainder = divmod(int(actual_duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            duration_text = f"{hours}h {minutes}m"
        elif minutes > 0:
            duration_text = f"{minutes}m {seconds}s"
        else:
            duration_text = f"{seconds}s"
        
        # Disable the button
        button.disabled = True
        button.label = f"✅ Restored after {duration_text}"
        button.style = discord.ButtonStyle.gray
        
        assert interaction.message is not None
        await interaction.message.edit(view=self)

        # Send restoration announcement
        embed = DowntimeEmbed.end(self.service, interaction.user, self.service_type)
        embed.add_field(name="⏱️ Actual Downtime", value=duration_text, inline=True)
        
        channel = self.announcement_channel or interaction.channel
        assert channel is not None
        await channel.send(embed=embed)
        
        # Close incident thread with summary
        if self.incident_thread:
            await self.incident_thread.send(
                f"✅ **Incident Resolved**\n\n"
                f"**Service:** {self.service}\n"
                f"**Duration:** {duration_text}\n"
                f"**Resolved by:** {interaction.user.mention}\n\n"
                f"*This thread will be archived.*"
            )
            await self.incident_thread.edit(archived=True, locked=True)
        
        await interaction.response.send_message(
            f"✅ **{self.service}** marked as restored!", 
            ephemeral=True
        )
        
        self.stop()
    
    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to cancel/dismiss the downtime (false alarm)"""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can cancel it.",
                ephemeral=True
            )
            return
        
        self.resolved = True
        
        # Cancel timer if running
        if self.timer_task:
            self.timer_task.cancel()
        
        # Resume UptimeKuma monitor if it was paused (false alarm)
        if self.uptimekuma_paused and uptimekuma_module.uptimekuma_auth_client:
            try:
                if self.uptimekuma_monitor_id:
                    await uptimekuma_module.uptimekuma_auth_client.resume_monitor(self.uptimekuma_monitor_id)
                else:
                    await uptimekuma_module.uptimekuma_auth_client.resume_monitor_by_name(self.service)
            except Exception as e:
                print(f"[UptimeKuma] Error resuming monitor on cancel: {e}")
        
        # Update the original message
        for child in self.children:
            child.disabled = True
        
        assert interaction.message is not None
        await interaction.message.edit(
            content=f"~~{interaction.message.content or ''}~~ **[CANCELLED]**",
            view=self
        )
        
        await interaction.response.send_message(
            f"🚫 Downtime announcement for **{self.service}** has been cancelled.",
            ephemeral=True
        )
        
        # Also archive the incident thread if it exists
        if self.incident_thread:
            await self.incident_thread.send("🚫 *Incident cancelled - false alarm*")
            await self.incident_thread.edit(archived=True)
        
        self.stop()
    
    async def on_timeout(self):
        """Called when the view times out (24h)"""
        if self.message and not self.resolved:
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
