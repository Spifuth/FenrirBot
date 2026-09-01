"""Downtime announcement commands"""

import discord
import json
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from ..config import config
from ..utils.embeds import DowntimeEmbed, ServiceType, MaintenanceType
from ..utils.docker import docker_manager
from ..utils.views import DowntimeView
from ..utils.incidents import IncidentRecord, incident_store
from ..utils.helpers import (
    get_announcement_channel,
    get_notification_mention,
    parse_local_datetime,
    format_paris,
)

@dataclass
class ScheduledMaintenance:
    """Represents a scheduled maintenance"""
    service: str
    scheduled_time: datetime
    duration: str
    reason: str
    author_id: int
    channel_id: int
    maintenance_type: str = "downtime"
    announced: bool = False
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        return {
            "service": self.service,
            "scheduled_time": self.scheduled_time.isoformat(),
            "duration": self.duration,
            "reason": self.reason,
            "author_id": self.author_id,
            "channel_id": self.channel_id,
            "maintenance_type": self.maintenance_type,
            "announced": self.announced
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledMaintenance":
        """Create from dict"""
        return cls(
            service=data["service"],
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]),
            duration=data["duration"],
            reason=data["reason"],
            author_id=data["author_id"],
            channel_id=data["channel_id"],
            maintenance_type=data.get("maintenance_type", "downtime"),
            announced=data.get("announced", False)
        )


# Path to the scheduled maintenances JSON file
SCHEDULED_FILE = Path(__file__).parent.parent.parent / "data" / "scheduled_maintenances.json"


class DowntimeCog(commands.Cog, name="Downtime"):
    """Commands for announcing service downtime and restoration"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._containers_cache: set[str] = set()
        self._stacks_cache: set[str] = set()
        self._scheduled_maintenances: list[ScheduledMaintenance] = []
        self._load_scheduled_maintenances()
        self.check_scheduled_maintenances.start()
    
    async def cog_unload(self):
        self.check_scheduled_maintenances.cancel()
    
    def _load_scheduled_maintenances(self):
        """Load scheduled maintenances from JSON file"""
        if SCHEDULED_FILE.exists():
            try:
                with open(SCHEDULED_FILE, "r") as f:
                    data = json.load(f)
                self._scheduled_maintenances = [
                    ScheduledMaintenance.from_dict(m) for m in data
                ]
                print(f"[Downtime] Loaded {len(self._scheduled_maintenances)} scheduled maintenance(s)")
            except Exception as e:
                print(f"[Downtime] Error loading scheduled maintenances: {e}")
                self._scheduled_maintenances = []
    
    def _save_scheduled_maintenances(self):
        """Save scheduled maintenances to JSON file"""
        try:
            SCHEDULED_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SCHEDULED_FILE, "w") as f:
                json.dump(
                    [m.to_dict() for m in self._scheduled_maintenances],
                    f,
                    indent=2
                )
        except Exception as e:
            print(f"[Downtime] Error saving scheduled maintenances: {e}")
    
    @tasks.loop(seconds=30)
    async def check_scheduled_maintenances(self):
        """Check every 30 seconds if a scheduled maintenance should trigger"""
        now = datetime.now(timezone.utc)
        triggered_any = False

        for maintenance in self._scheduled_maintenances[:]:
            if maintenance.announced:
                continue

            if now >= maintenance.scheduled_time:
                # Check if it's a catchup (more than 5 minutes late)
                is_catchup = (now - maintenance.scheduled_time).total_seconds() > 300
                try:
                    sent = await self._trigger_scheduled_downtime(maintenance, is_catchup=is_catchup)
                except Exception as e:
                    # One bad entry must never end the loop — tasks.loop stops on an
                    # unhandled exception, which would silence every future maintenance.
                    print(f"[Downtime] Trigger failed for {maintenance.service}: {e!r}")
                    continue
                if not sent:
                    # Keep it queued rather than deleting it unannounced.
                    continue
                maintenance.announced = True
                triggered_any = True
        
        # Clean up old announced maintenances and save
        old_count = len(self._scheduled_maintenances)
        self._scheduled_maintenances = [
            m for m in self._scheduled_maintenances 
            if not m.announced
        ]
        
        if triggered_any or len(self._scheduled_maintenances) != old_count:
            self._save_scheduled_maintenances()
    
    @check_scheduled_maintenances.before_loop
    async def before_check_scheduled(self):
        await self.bot.wait_until_ready()
        # Check for missed maintenances on startup
        await self._catchup_missed_maintenances()
    
    async def _catchup_missed_maintenances(self):
        """Trigger any maintenances that were missed while bot was offline"""
        now = datetime.now(timezone.utc)
        missed = [m for m in self._scheduled_maintenances if now >= m.scheduled_time and not m.announced]
        
        if missed:
            print(f"[Downtime] Found {len(missed)} missed maintenance(s), triggering catchup...")
            for maintenance in missed:
                try:
                    sent = await self._trigger_scheduled_downtime(maintenance, is_catchup=True)
                except Exception as e:
                    print(f"[Downtime] Catchup failed for {maintenance.service}: {e!r}")
                    continue
                if sent:
                    maintenance.announced = True
            
            # Clean up and save
            self._scheduled_maintenances = [
                m for m in self._scheduled_maintenances 
                if not m.announced
            ]
            self._save_scheduled_maintenances()
    
    async def _trigger_scheduled_downtime(
        self, maintenance: ScheduledMaintenance, is_catchup: bool = False
    ) -> bool:
        """Announce a scheduled maintenance. Returns True only if it was sent."""
        channel = self.bot.get_channel(maintenance.channel_id)
        # TextChannel or Thread: /scheduled captures interaction.channel.id with
        # no type check, so a maintenance scheduled from inside a thread stores a
        # thread id. Thread.send() works fine; only the incident-thread creation
        # below doesn't apply there, and that's already best-effort.
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            print(
                f"[Downtime] Channel {maintenance.channel_id} unavailable for "
                f"{maintenance.service}; leaving it queued"
            )
            return False

        # get_user only reads the cache; fall back to the API, and tolerate a
        # user who has left. The embed renders "inconnu" rather than crashing.
        author = self.bot.get_user(maintenance.author_id)
        if author is None:
            try:
                author = await self.bot.fetch_user(maintenance.author_id)
            except discord.HTTPException:
                author = None
        service_type = self._get_service_type(maintenance.service)

        try:
            maint_type = MaintenanceType(maintenance.maintenance_type)
        except ValueError:
            maint_type = MaintenanceType.DOWNTIME
        
        embed = DowntimeEmbed.maintenance(
            maintenance.service,
            f"[SCHEDULED] {maintenance.reason}",
            maintenance.duration,
            author,
            service_type,
            maint_type,
        )

        notification_mention = get_notification_mention()

        # Create interactive view with restore button
        view = DowntimeView(
            service=maintenance.service,
            author_id=maintenance.author_id,
            duration_str=maintenance.duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=service_type,
            maintenance_type=maint_type,
        )
        
        # Customize message based on catchup status
        if is_catchup:
            delay_minutes = int((datetime.now(timezone.utc) - maintenance.scheduled_time).total_seconds() / 60)
            content = f"{notification_mention} ⚠️ **Maintenance planifiée (retard {delay_minutes}min - bot hors ligne)**"
        else:
            content = f"{notification_mention} ⏰ **Maintenance planifiée démarrant maintenant!**"
        
        msg = await channel.send(
            content=content,
            embed=embed,
            view=view
        )
        view.message = msg

        try:
            incident_store.add(IncidentRecord(
                message_id=msg.id,
                channel_id=channel.id,
                service=maintenance.service,
                author_id=maintenance.author_id,
                duration_str=maintenance.duration,
                service_type=service_type.value,
                maintenance_type=maint_type.value,
                started_at=datetime.now(timezone.utc).isoformat(),
            ))
        except Exception as e:
            print(f"[Downtime] Could not persist incident {msg.id}: {e!r}")

        # The announcement is public from here: the role has been pinged. A
        # failure below must never bubble up, because the caller would leave
        # the entry unannounced and the 30s loop would re-ping every tick.
        try:
            thread = await msg.create_thread(
                name=f"{maint_type.icon} {maintenance.service} - {maint_type.label}",
                auto_archive_duration=1440
            )
            catchup_note = ""
            if is_catchup:
                catchup_note = f"\n⚠️ **Note:** This maintenance was triggered late because the bot was offline.\n"
            await thread.send(
                f"📋 **Scheduled Maintenance Thread** for **{maintenance.service}**\n\n"
                f"⏰ This maintenance was scheduled and has now started automatically.\n"
                f"📝 Reason: {maintenance.reason}\n"
                f"⏱️ Expected duration: {maintenance.duration}"
                f"{catchup_note}"
            )
            view.incident_thread = thread
        except Exception as e:
            print(f"[Downtime] Incident thread failed for {maintenance.service}: {e!r}")

        await view.start_timer()
        return True

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

    async def container_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for containers only"""
        self._refresh_service_cache()
        
        choices = []
        for name in self._containers_cache:
            if not current or current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        
        choices.sort(key=lambda c: c.name)
        return choices[:25]

    async def stack_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for stacks only"""
        self._refresh_service_cache()
        
        choices = []
        for name in self._stacks_cache:
            if not current or current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        
        choices.sort(key=lambda c: c.name)
        return choices[:25]

    # ========== Slash Commands ==========

    @app_commands.command(name="up", description="🟢 Annoncer la restauration d'un service")
    @app_commands.describe(
        service="Nom du service rétabli",
        mention="Mentionner le rôle de notification (défaut: Non)"
    )
    @app_commands.autocomplete(service=service_autocomplete)
    async def up_slash(self, interaction: discord.Interaction, service: str, mention: bool = False):
        """Announce service restoration via slash command"""
        channel = get_announcement_channel(self.bot, interaction.channel)
        service_type = self._get_service_type(service)
        embed = DowntimeEmbed.end(service, interaction.user, service_type)

        assert channel is not None
        await channel.send(
            content=get_notification_mention() if mention else None,
            embed=embed
        )

        # The service is back up: drop any still-open incident record for it
        # so a future restart doesn't revive enabled buttons on a closed
        # announcement (a late click would post a fabricated duration). A
        # store failure here must never break the announcement, which has
        # already been sent.
        try:
            removed = incident_store.remove_by_service(service)
            if removed:
                print(f"[Downtime] Pruned {removed} closed incident record(s) for {service}")
        except Exception as e:
            print(f"[Downtime] Could not prune incident store for {service}: {e!r}")

        response = f"✅ Annonce de restauration envoyée pour **{service}** ({service_type.label})"
        await interaction.response.send_message(response, ephemeral=True)

    @app_commands.command(name="maintenance", description="🔧 Annoncer une maintenance (màj, backup, config, etc.)")
    @app_commands.describe(
        service="Nom du service",
        maintenance_type="Type de maintenance",
        reason="Détails sur la maintenance",
        duration="Durée estimée (ex: '30 minutes', '2 heures')",
        service_type="Type de service (auto-détecté si non spécifié)",
        mention="Mentionner le rôle de notification (défaut: Oui)"
    )
    @app_commands.choices(maintenance_type=[
        app_commands.Choice(name="🔧 Interruption", value="downtime"),
        app_commands.Choice(name="⬆️ Mise à jour", value="update"),
        app_commands.Choice(name="💾 Sauvegarde", value="backup"),
        app_commands.Choice(name="⚙️ Config", value="config"),
        app_commands.Choice(name="🔒 Patch sécurité", value="security"),
        app_commands.Choice(name="🚚 Migration", value="migration"),
        app_commands.Choice(name="🛠️ Autre", value="other"),
    ])
    @app_commands.choices(service_type=[
        app_commands.Choice(name="🐳 Container", value="container"),
        app_commands.Choice(name="📚 Stack", value="stack"),
        app_commands.Choice(name="📦 Autre service", value="other"),
    ])
    @app_commands.autocomplete(service=service_autocomplete)
    async def maintenance_slash(
        self,
        interaction: discord.Interaction,
        service: str,
        maintenance_type: str,
        reason: str,
        duration: str = "Inconnue",
        service_type: str | None = None,
        mention: bool = True
    ):
        """Announce a maintenance action (update, backup, etc.) via slash command"""
        channel = get_announcement_channel(self.bot, interaction.channel)
        
        # Determine service type
        if service_type:
            svc_type = ServiceType(service_type)
        else:
            svc_type = self._get_service_type(service)
        
        # Get maintenance type enum
        try:
            maint_type = MaintenanceType(maintenance_type)
        except ValueError:
            maint_type = MaintenanceType.OTHER
        
        embed = DowntimeEmbed.maintenance(
            service, reason, duration, interaction.user, svc_type, maint_type
        )

        notification_mention = get_notification_mention() if mention else None

        # Create interactive view with restore button
        view = DowntimeView(
            service=service,
            author_id=interaction.user.id,
            duration_str=duration,
            announcement_channel=channel,
            notification_mention=notification_mention,
            service_type=svc_type,
            maintenance_type=maint_type,
        )

        # Send announcement with buttons
        assert channel is not None
        msg = await channel.send(
            content=notification_mention,
            embed=embed,
            view=view
        )
        view.message = msg

        try:
            incident_store.add(IncidentRecord(
                message_id=msg.id,
                channel_id=channel.id,
                service=service,
                author_id=interaction.user.id,
                duration_str=duration,
                service_type=svc_type.value,
                maintenance_type=maint_type.value,
                started_at=datetime.now(timezone.utc).isoformat(),
            ))
        except Exception as e:
            print(f"[Downtime] Could not persist incident {msg.id}: {e!r}")

        # Create thread for updates
        thread = await msg.create_thread(
            name=f"{maint_type.icon} {service} - {maint_type.label}",
            auto_archive_duration=1440
        )
        await thread.send(
            f"📋 **Fil {maint_type.label}** pour **{service}**\n\n"
            f"Utilisez ce fil pour:\n"
            f"• Poster des mises à jour\n"
            f"• Partager logs ou statut\n"
            f"• Coordonner avec les autres\n\n"
            f"*Le fil sera archivé après 24h d'inactivité*"
        )
        view.incident_thread = thread
        
        # Build response message
        response_parts = [
            f"✅ {maint_type.icon} Annonce **{maint_type.label}** envoyée pour **{service}** ({svc_type.label})",
            f"💬 Fil créé: {thread.mention}",
            f"💡 Cliquez sur le bouton de l'annonce pour marquer comme terminé."
        ]

        await interaction.response.send_message(
            "\n".join(response_parts),
            ephemeral=True
        )

    @app_commands.command(name="scheduled", description="📅 Planifier une maintenance future")
    @app_commands.describe(
        service="Nom du service",
        when="Date/heure (format: YYYY-MM-DD HH:MM, ex: '2026-01-15 22:00')",
        duration="Durée estimée (ex: '30 minutes', '2 heures')",
        reason="Raison de la maintenance",
        maintenance_type="Type de maintenance (défaut: downtime)",
        mention="Mentionner le rôle de notification (défaut: Oui)"
    )
    @app_commands.choices(maintenance_type=[
        app_commands.Choice(name="🔧 Interruption", value="downtime"),
        app_commands.Choice(name="⬆️ Mise à jour", value="update"),
        app_commands.Choice(name="💾 Sauvegarde", value="backup"),
        app_commands.Choice(name="⚙️ Config", value="config"),
        app_commands.Choice(name="🔒 Patch sécurité", value="security"),
        app_commands.Choice(name="🚚 Migration", value="migration"),
        app_commands.Choice(name="🛠️ Autre", value="other"),
    ])
    @app_commands.autocomplete(service=service_autocomplete)
    async def scheduled_slash(
        self, 
        interaction: discord.Interaction, 
        service: str, 
        when: str, 
        duration: str, 
        reason: str,
        maintenance_type: str = "downtime",
        mention: bool = True
    ):
        """Announce scheduled maintenance via slash command with auto-trigger"""
        # Parse the datetime
        try:
            scheduled_time = parse_local_datetime(when)
        except ValueError:
            await interaction.response.send_message(
                "❌ Format de date invalide ! Utilisez: `YYYY-MM-DD HH:MM`\n"
                "Exemple: `2026-01-15 22:00`",
                ephemeral=True
            )
            return
        
        # Check if the time is in the future
        if scheduled_time <= datetime.now(timezone.utc):
            await interaction.response.send_message(
                "❌ La date doit être dans le futur !",
                ephemeral=True
            )
            return
        
        channel = get_announcement_channel(self.bot, interaction.channel)
        service_type = self._get_service_type(service)
        
        # Get maintenance type enum
        try:
            maint_type = MaintenanceType(maintenance_type)
        except ValueError:
            maint_type = MaintenanceType.DOWNTIME
        
        # Format the time nicely for display
        # scheduled_time is UTC; the user typed Paris local, so render it back in Paris
        when_display = format_paris(scheduled_time, "%A %d %B %Y à %H:%M")
        embed = DowntimeEmbed.scheduled(
            service, when_display, duration, reason, 
            interaction.user, service_type, maint_type
        )
        
        # Add auto-trigger info to embed
        embed.add_field(
            name="⏰ Déclenchement auto",
            value=f"{maint_type.label} démarrera automatiquement le <t:{int(scheduled_time.timestamp())}:F>",
            inline=False
        )
        
        assert channel is not None
        assert interaction.channel is not None
        await channel.send(
            content=get_notification_mention() if mention else None,
            embed=embed
        )

        # Schedule the automatic trigger
        maintenance = ScheduledMaintenance(
            service=service,
            scheduled_time=scheduled_time,
            duration=duration,
            reason=reason,
            author_id=interaction.user.id,
            channel_id=interaction.channel.id,
            maintenance_type=maintenance_type
        )
        self._scheduled_maintenances.append(maintenance)
        self._save_scheduled_maintenances()
        
        await interaction.response.send_message(
            f"✅ Maintenance **{maint_type.label.lower()}** planifiée pour **{service}** ({service_type.label})\n"
            f"⏰ {maint_type.label} se déclenchera automatiquement le <t:{int(scheduled_time.timestamp())}:F>\n"
            f"📋 {len(self._scheduled_maintenances)} maintenance(s) planifiée(s)\n"
            f"💾 Sauvegardé sur disque (persistera après redémarrage)",
            ephemeral=True
        )
    
    @app_commands.command(name="scheduled-list", description="📋 Lister les maintenances planifiées")
    async def scheduled_list_slash(self, interaction: discord.Interaction):
        """List all pending scheduled maintenances"""
        if not self._scheduled_maintenances:
            await interaction.response.send_message(
                "📋 Aucune maintenance planifiée.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Maintenances planifiées",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        for i, m in enumerate(self._scheduled_maintenances, 1):
            try:
                maint_type = MaintenanceType(m.maintenance_type)
            except ValueError:
                maint_type = MaintenanceType.DOWNTIME

            embed.add_field(
                name=f"{i}. {m.service}",
                value=(
                    f"```\n"
                    f"Type : {maint_type.label}\n"
                    f"Durée: {m.duration}\n"
                    f"```"
                    f"\nDéclenchement : <t:{int(m.scheduled_time.timestamp())}:F>"
                    f"\nRaison : {m.reason[:900]}"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="scheduled-cancel", description="❌ Annuler une maintenance planifiée")
    @app_commands.describe(service="Nom du service dont la maintenance doit être annulée")
    @app_commands.autocomplete(service=service_autocomplete)
    async def scheduled_cancel_slash(self, interaction: discord.Interaction, service: str):
        """Cancel a scheduled maintenance"""
        for m in self._scheduled_maintenances[:]:
            if m.service.lower() == service.lower():
                self._scheduled_maintenances.remove(m)
                self._save_scheduled_maintenances()
                await interaction.response.send_message(
                    f"✅ Maintenance planifiée pour **{service}** annulée.\n"
                    f"💾 Modifications sauvegardées.",
                    ephemeral=True
                )
                return
        
        await interaction.response.send_message(
            f"❌ Aucune maintenance planifiée pour **{service}**",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DowntimeCog(bot))
