"""Interactive views (buttons, modals) for Fenrir Bot"""

import discord
from discord import ui
from datetime import datetime, timedelta, timezone
import asyncio
import re

from .embeds import DowntimeEmbed, MaintenanceType, ServiceType
from .incidents import IncidentRecord, IncidentStore, incident_store


def parse_duration(duration_str: str) -> timedelta | None:
    """Parse a duration string like '30 minutes', '2 hours', '1h30m' into timedelta"""
    duration_str = duration_str.lower().strip()

    total_seconds = 0

    hours_match = re.search(r'(\d+)\s*(?:hours?|h)', duration_str)
    if hours_match:
        total_seconds += int(hours_match.group(1)) * 3600

    mins_match = re.search(r'(\d+)\s*(?:minutes?|mins?|m(?!o))', duration_str)
    if mins_match:
        total_seconds += int(mins_match.group(1)) * 60

    secs_match = re.search(r'(\d+)\s*(?:seconds?|secs?|s)', duration_str)
    if secs_match:
        total_seconds += int(secs_match.group(1))

    if total_seconds > 0:
        return timedelta(seconds=total_seconds)

    return None


class DowntimeView(ui.View):
    """Interactive view for maintenance announcements with restore and cancel buttons"""

    def __init__(
        self,
        service: str,
        author_id: int,
        duration_str: str = "Unknown",
        announcement_channel: discord.abc.Messageable | None = None,
        notification_mention: str | None = "@here",
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: MaintenanceType = MaintenanceType.DOWNTIME,
        store: IncidentStore | None = None,
        started_at: datetime | None = None,
    ):
        # timeout=None + stable custom_ids => discord.py treats this as a
        # persistent view, so bot.add_view() can revive it after a restart.
        super().__init__(timeout=None)
        self.store = store or incident_store
        self.service = service
        self.author_id = author_id
        self.duration_str = duration_str
        self.announcement_channel = announcement_channel
        self.notification_mention = notification_mention
        self.service_type = service_type
        self.maintenance_type = maintenance_type
        self.restore_button.label = {
            MaintenanceType.DOWNTIME:   "✅ Service restauré",
            MaintenanceType.UPDATE:     "✅ Mise à jour terminée",
            MaintenanceType.BACKUP:     "✅ Sauvegarde terminée",
            MaintenanceType.CONFIG:     "✅ Config appliquée",
            MaintenanceType.SECURITY:   "✅ Patch appliqué",
            MaintenanceType.MIGRATION:  "✅ Migration terminée",
            MaintenanceType.OTHER:      "✅ Maintenance terminée",
        }[maintenance_type]
        self.resolved = False
        self.message: discord.Message | None = None
        self.timer_task: asyncio.Task | None = None
        self.incident_thread: discord.Thread | None = None

        self.duration = parse_duration(duration_str)
        self.start_time = started_at if started_at is not None else datetime.now(timezone.utc)

    async def start_timer(self):
        """Start a background timer that reminds when duration is up"""
        if not self.duration:
            return

        async def timer_callback():
            try:
                await asyncio.sleep(self.duration.total_seconds())

                if not self.resolved and self.message:
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

    @ui.button(label="✅ Service Restored", style=discord.ButtonStyle.green,
               custom_id="fenrir:incident:restore")
    async def restore_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to mark service as restored"""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can mark it as restored.",
                ephemeral=True
            )
            return

        # Four REST calls follow; Discord's initial-response deadline is 3s.
        await interaction.response.defer(ephemeral=True)

        self.resolved = True

        if self.timer_task:
            self.timer_task.cancel()

        actual_duration = datetime.now(timezone.utc) - self.start_time
        hours, remainder = divmod(int(actual_duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            duration_text = f"{hours}h {minutes}m"
        elif minutes > 0:
            duration_text = f"{minutes}m {seconds}s"
        else:
            duration_text = f"{seconds}s"

        button.disabled = True
        button.label = f"✅ Restored after {duration_text}"
        button.style = discord.ButtonStyle.gray

        assert interaction.message is not None
        await interaction.message.edit(view=self)

        embed = DowntimeEmbed.end(self.service, interaction.user, self.service_type, self.maintenance_type)
        embed.add_field(name="⏱️ Actual Downtime", value=duration_text, inline=True)

        channel = self.announcement_channel or interaction.channel
        assert channel is not None
        await channel.send(embed=embed)

        if self.incident_thread:
            await self.incident_thread.send(
                f"✅ **Incident Resolved**\n\n"
                f"**Service:** {self.service}\n"
                f"**Duration:** {duration_text}\n"
                f"**Resolved by:** {interaction.user.mention}\n\n"
                f"*This thread will be archived.*"
            )
            await self.incident_thread.edit(archived=True, locked=True)

        if interaction.message is not None:
            self.store.remove(interaction.message.id)

        await interaction.followup.send(
            f"✅ **{self.service}** marked as restored!",
            ephemeral=True
        )

        self.stop()

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.red,
               custom_id="fenrir:incident:cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to cancel/dismiss the downtime (false alarm)"""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the person who announced the downtime can cancel it.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        self.resolved = True

        if self.timer_task:
            self.timer_task.cancel()

        for child in self.children:
            child.disabled = True

        assert interaction.message is not None
        await interaction.message.edit(
            content=f"~~{interaction.message.content or ''}~~ **[CANCELLED]**",
            view=self
        )

        if interaction.message is not None:
            self.store.remove(interaction.message.id)

        await interaction.followup.send(
            f"🚫 Downtime announcement for **{self.service}** has been cancelled.",
            ephemeral=True
        )

        if self.incident_thread:
            await self.incident_thread.send("🚫 *Incident cancelled - false alarm*")
            await self.incident_thread.edit(archived=True)

        self.stop()

    async def on_timeout(self):
        """Called when the view times out.

        The view is constructed with timeout=None (persistent), so this
        never fires in normal operation. Kept only in case something ever
        constructs a DowntimeView with a non-None timeout.
        """
        if self.message and not self.resolved:
            for child in self.children:
                child.disabled = True

            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    @classmethod
    def from_record(cls, record: IncidentRecord, store: IncidentStore) -> "DowntimeView":
        """Rebuild a view from disk after a restart."""
        try:
            service_type = ServiceType(record.service_type)
        except ValueError:
            service_type = ServiceType.OTHER
        try:
            maintenance_type = MaintenanceType(record.maintenance_type)
        except ValueError:
            maintenance_type = MaintenanceType.DOWNTIME
        # Fall back to "now" on a missing or unparseable timestamp rather
        # than raising -- a bad/old record must still revive the buttons.
        started_at = None
        if record.started_at:
            try:
                parsed = datetime.fromisoformat(record.started_at)
            except ValueError:
                started_at = None
            else:
                # A value with no UTC offset parses fine but yields a naive
                # datetime; the restore button later subtracts it from an
                # aware datetime.now(timezone.utc), which raises TypeError.
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                started_at = parsed
        return cls(
            service=record.service,
            author_id=record.author_id,
            duration_str=record.duration_str,
            service_type=service_type,
            maintenance_type=maintenance_type,
            store=store,
            started_at=started_at,
        )
