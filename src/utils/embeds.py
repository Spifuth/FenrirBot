"""Discord embed builders for announcements"""

import discord
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ServiceType(Enum):
    """Type of service being announced"""
    CONTAINER = "container"
    STACK = "stack"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {
            ServiceType.CONTAINER: "Container",
            ServiceType.STACK: "Stack",
            ServiceType.OTHER: "Service",
        }[self]


class MaintenanceType(Enum):
    """Type of maintenance being performed"""
    DOWNTIME = "downtime"
    UPDATE = "update"
    BACKUP = "backup"
    CONFIG = "config"
    SECURITY = "security"
    MIGRATION = "migration"
    OTHER = "other"

    @property
    def icon(self) -> str:
        """Kept for backward compatibility with downtime cog scheduled-list."""
        return {
            MaintenanceType.DOWNTIME: "▼",
            MaintenanceType.UPDATE: "↑",
            MaintenanceType.BACKUP: "◼",
            MaintenanceType.CONFIG: "≡",
            MaintenanceType.SECURITY: "◆",
            MaintenanceType.MIGRATION: "→",
            MaintenanceType.OTHER: "·",
        }[self]

    @property
    def label(self) -> str:
        return {
            MaintenanceType.DOWNTIME: "Interruption",
            MaintenanceType.UPDATE: "Mise à jour",
            MaintenanceType.BACKUP: "Sauvegarde",
            MaintenanceType.CONFIG: "Configuration",
            MaintenanceType.SECURITY: "Sécurité",
            MaintenanceType.MIGRATION: "Migration",
            MaintenanceType.OTHER: "Maintenance",
        }[self]

    @property
    def verb(self) -> str:
        return {
            MaintenanceType.DOWNTIME: "hors ligne",
            MaintenanceType.UPDATE: "en cours de mise à jour",
            MaintenanceType.BACKUP: "en cours de sauvegarde",
            MaintenanceType.CONFIG: "en reconfiguration",
            MaintenanceType.SECURITY: "en cours de patching",
            MaintenanceType.MIGRATION: "en cours de migration",
            MaintenanceType.OTHER: "en maintenance",
        }[self]


def _bar(value: float, width: int = 10) -> str:
    """Render a fixed-width ASCII progress bar using █ and ·."""
    filled = round(max(0.0, min(value, 100.0)) / 100 * width)
    return "[" + "█" * filled + "·" * (width - filled) + "]"


class DowntimeEmbed:
    """Helper class to create consistent downtime embeds"""

    @staticmethod
    def start(
        service: str,
        reason: str,
        estimated_duration: str,
        author: discord.User | discord.Member,
        service_type: ServiceType = ServiceType.OTHER,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"Interruption · {service}",
            description=f"{service_type.label} hors ligne",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Durée estimée", value=f"```\n{estimated_duration}\n```", inline=True)
        embed.add_field(name="Raison", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Downtime · {author.display_name}")
        return embed

    @staticmethod
    def maintenance(
        service: str,
        reason: str,
        estimated_duration: str,
        author: discord.User | discord.Member,
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: MaintenanceType | None = None,
    ) -> discord.Embed:
        if maintenance_type is None:
            maintenance_type = MaintenanceType.OTHER
        embed = discord.Embed(
            title=f"{maintenance_type.label} · {service}",
            description=f"{service_type.label} {maintenance_type.verb}",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Type", value=f"```\n{maintenance_type.label}\n```", inline=True)
        embed.add_field(name="Durée estimée", value=f"```\n{estimated_duration}\n```", inline=True)
        embed.add_field(name="Détails", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Maintenance · {author.display_name}")
        return embed

    @staticmethod
    def end(
        service: str,
        author: discord.User | discord.Member,
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: MaintenanceType | None = None,
    ) -> discord.Embed:
        if maintenance_type is None:
            title = f"Service rétabli · {service}"
        else:
            title = f"{maintenance_type.label} terminée · {service}"
        embed = discord.Embed(
            title=title,
            description=f"{service_type.label} opérationnel",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Statut", value="```\nOPERATIONNEL\n```", inline=True)
        embed.set_footer(text=f"Fenrir · Downtime · {author.display_name}")
        return embed

    @staticmethod
    def scheduled(
        service: str,
        scheduled_time: str,
        duration: str,
        reason: str,
        author: discord.User | discord.Member,
        service_type: ServiceType = ServiceType.OTHER,
        maintenance_type: MaintenanceType | None = None,
    ) -> discord.Embed:
        if maintenance_type is None:
            maintenance_type = MaintenanceType.DOWNTIME
        embed = discord.Embed(
            title=f"{maintenance_type.label} planifié · {service}",
            description=f"{service_type.label}",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Type", value=f"```\n{maintenance_type.label}\n```", inline=True)
        embed.add_field(name="Date", value=f"```\n{scheduled_time}\n```", inline=True)
        embed.add_field(name="Durée", value=f"```\n{duration}\n```", inline=True)
        embed.add_field(name="Détails", value=f"```\n{reason}\n```", inline=False)
        embed.set_footer(text=f"Fenrir · Planifié · {author.display_name}")
        return embed

    @staticmethod
    def status(message: str, author: discord.User | discord.Member) -> discord.Embed:
        embed = discord.Embed(
            title="Mise à jour de statut",
            description=message,
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Fenrir · Statut · {author.display_name}")
        return embed


class DashboardEmbed:
    """Embed builders for dashboard displays"""

    @staticmethod
    def docker_status(containers: list[Any], running: list[Any], stopped: list[Any]) -> discord.Embed:
        total = len(containers)
        running_pct = (len(running) / total * 100) if total > 0 else 0

        embed = discord.Embed(
            title="Docker",
            description=f"```\n{_bar(running_pct)}  {len(running)}/{total} en cours\n```",
            color=0x2C2F33,
            timestamp=datetime.now(timezone.utc),
        )

        if running:
            lines = []
            for c in running[:12]:
                suffix = ""
                if "healthy" in c.status.lower():
                    suffix = " ok"
                elif "unhealthy" in c.status.lower():
                    suffix = " err"
                lines.append(f"{c.display_name}{suffix}")
            if len(running) > 12:
                lines.append(f"+{len(running) - 12} autres")
            embed.add_field(
                name=f"En cours ({len(running)})",
                value="```\n" + "\n".join(lines) + "\n```",
                inline=True,
            )

        if stopped:
            lines = [c.display_name for c in stopped[:8]]
            if len(stopped) > 8:
                lines.append(f"+{len(stopped) - 8} autres")
            embed.add_field(
                name=f"Arrêtés ({len(stopped)})",
                value="```\n" + "\n".join(lines) + "\n```",
                inline=True,
            )

        embed.set_footer(text="Fenrir · Docker")
        return embed
