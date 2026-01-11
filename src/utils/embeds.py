"""Discord embed builders for announcements"""

import discord
from datetime import datetime
from enum import Enum


class ServiceType(Enum):
    """Type of service being announced"""
    CONTAINER = "container"
    STACK = "stack"
    OTHER = "other"
    
    @property
    def icon(self) -> str:
        """Get the icon for this service type"""
        return {
            ServiceType.CONTAINER: "🐳",
            ServiceType.STACK: "📚",
            ServiceType.OTHER: "📦"
        }.get(self, "📦")
    
    @property
    def label(self) -> str:
        """Get the label for this service type"""
        return {
            ServiceType.CONTAINER: "Container",
            ServiceType.STACK: "Stack",
            ServiceType.OTHER: "Service"
        }.get(self, "Service")


class EmbedAssets:
    """URLs for embed images and GIFs"""
    
    # Using twemoji CDN (Twitter emoji images) - guaranteed to work with Discord
    # Downtime / Alerts
    DOWNTIME_GIF = "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExcDd2MzBhOGw3a3Q0YnV1aXhiNm9nbGx0cWV4dHU3cDQ3Ymt6NXJuaiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/xTiTnrliW65rlwud8I/giphy.gif"
    DOWNTIME_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f6a8.png"  # 🚨 Red siren
    
    # Restored / Success
    RESTORED_GIF = "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExYnB1dXBjNnNhdjJ2OHdjcTJxbGRyODM0NzNub3VicHRyMWw0OXp0ZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3ohzdIuqJoo8QdKlnW/giphy.gif"
    RESTORED_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/2705.png"  # ✅ Green check
    
    # Scheduled / Warning
    SCHEDULED_GIF = "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExd2Q4eGF6NmQ1eGRzanVwbGUxcnR0c3EzeWJocHptcHZ5aml2NWRvdyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l0HlBO7eyXzSZkJri/giphy.gif"
    SCHEDULED_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4c5.png"  # 📅 Calendar
    
    # Status / Info
    STATUS_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/2139.png"  # ℹ️ Info
    
    # Dashboard
    DASHBOARD_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4ca.png"  # 📊 Chart
    
    # Fenrir branding - Wolf icon
    FENRIR_ICON = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f43a.png"  # 🐺 Wolf


def progress_bar(percentage: float, length: int = 10) -> str:
    """Create a visual progress bar"""
    filled = int(percentage / 100 * length)
    empty = length - filled
    
    if percentage >= 99:
        bar_char = "🟩"
        empty_char = "⬜"
    elif percentage >= 90:
        bar_char = "🟨"
        empty_char = "⬜"
    else:
        bar_char = "🟥"
        empty_char = "⬜"
    
    return bar_char * filled + empty_char * empty


def format_duration_fancy(duration: str) -> str:
    """Format duration with emoji"""
    if duration.lower() == "unknown":
        return "⏳ Unknown"
    return f"⏱️ {duration}"


class DowntimeEmbed:
    """Helper class to create consistent downtime embeds"""
    
    @staticmethod
    def start(
        service: str, 
        reason: str, 
        estimated_duration: str, 
        author: discord.Member,
        service_type: ServiceType = ServiceType.OTHER
    ) -> discord.Embed:
        """Create a downtime start announcement embed"""
        embed = discord.Embed(
            title="⚠️ DOWNTIME ALERT",
            description=(
                f"```ansi\n"
                f"\u001b[1;31m█▀▀ █▀▀ █▀█ █░█ █ █▀▀ █▀▀   █▀▄ █▀█ █░█░█ █▄░█\n"
                f"\u001b[1;31m▄▄█ ██▄ █▀▄ ▀▄▀ █ █▄▄ ██▄   █▄▀ █▄█ ▀▄▀▄▀ █░▀█\n"
                f"```\n"
                f"**{service}** is going offline for maintenance"
            ),
            color=0xFF4444,  # Bright red
            timestamp=datetime.now()
        )
        
        # Main info in a nice format
        embed.add_field(
            name=f"{service_type.icon} {service_type.label}",
            value=f"```\n{service}\n```",
            inline=True
        )
        embed.add_field(
            name="⏱️ Est. Duration",
            value=f"```\n{estimated_duration}\n```",
            inline=True
        )
        embed.add_field(
            name="\u200b",  # Empty field for spacing
            value="\u200b",
            inline=True
        )
        embed.add_field(
            name="📝 Reason",
            value=f">>> {reason}",
            inline=False
        )
        
        # Visual elements
        embed.set_thumbnail(url=EmbedAssets.DOWNTIME_THUMB)
        embed.set_image(url=EmbedAssets.DOWNTIME_GIF)
        
        # Footer with author
        embed.set_footer(
            text=f"🐺 Fenrir • Announced by {author.display_name}",
            icon_url=author.avatar.url if author.avatar else EmbedAssets.FENRIR_ICON
        )
        
        return embed
    
    @staticmethod
    def end(
        service: str, 
        author: discord.Member,
        service_type: ServiceType = ServiceType.OTHER
    ) -> discord.Embed:
        """Create a service restored announcement embed"""
        embed = discord.Embed(
            title="✅ SERVICE RESTORED",
            description=(
                f"```ansi\n"
                f"\u001b[1;32m█▀▀ █▀▀ █▀█ █░█ █ █▀▀ █▀▀   █░█ █▀█\n"
                f"\u001b[1;32m▄▄█ ██▄ █▀▄ ▀▄▀ █ █▄▄ ██▄   █▄█ █▀▀\n"
                f"```\n"
                f"**{service}** is back online and operational! 🎉"
            ),
            color=0x44FF44,  # Bright green
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name=f"{service_type.icon} {service_type.label}",
            value=f"```\n{service}\n```",
            inline=True
        )
        embed.add_field(
            name="📊 Status",
            value=f"```diff\n+ OPERATIONAL\n```",
            inline=True
        )
        
        # Visual elements
        embed.set_thumbnail(url=EmbedAssets.RESTORED_THUMB)
        embed.set_image(url=EmbedAssets.RESTORED_GIF)
        
        embed.set_footer(
            text=f"🐺 Fenrir • Restored by {author.display_name}",
            icon_url=author.avatar.url if author.avatar else EmbedAssets.FENRIR_ICON
        )
        
        return embed
    
    @staticmethod
    def scheduled(
        service: str, 
        scheduled_time: str, 
        duration: str, 
        reason: str, 
        author: discord.Member,
        service_type: ServiceType = ServiceType.OTHER
    ) -> discord.Embed:
        """Create a scheduled maintenance announcement embed"""
        embed = discord.Embed(
            title="📅 SCHEDULED MAINTENANCE",
            description=(
                f"```ansi\n"
                f"\u001b[1;33m█▀█ █░░ ▄▀█ █▄░█ █▄░█ █▀▀ █▀▄\n"
                f"\u001b[1;33m█▀▀ █▄▄ █▀█ █░▀█ █░▀█ ██▄ █▄▀\n"
                f"```\n"
                f"**{service}** has upcoming scheduled maintenance"
            ),
            color=0xFFAA00,  # Orange
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name=f"{service_type.icon} {service_type.label}",
            value=f"```\n{service}\n```",
            inline=True
        )
        embed.add_field(
            name="📅 When",
            value=f"```\n{scheduled_time}\n```",
            inline=True
        )
        embed.add_field(
            name="⏱️ Duration",
            value=f"```\n{duration}\n```",
            inline=True
        )
        embed.add_field(
            name="📝 Details",
            value=f">>> {reason}",
            inline=False
        )
        
        # Visual elements
        embed.set_thumbnail(url=EmbedAssets.SCHEDULED_THUMB)
        embed.set_image(url=EmbedAssets.SCHEDULED_GIF)
        
        embed.set_footer(
            text=f"🐺 Fenrir • Scheduled by {author.display_name}",
            icon_url=author.avatar.url if author.avatar else EmbedAssets.FENRIR_ICON
        )
        
        return embed
    
    @staticmethod
    def status(message: str, author: discord.Member) -> discord.Embed:
        """Create a general status update embed"""
        embed = discord.Embed(
            title="📢 STATUS UPDATE",
            description=f">>> {message}",
            color=0x5865F2,  # Discord blurple
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=EmbedAssets.STATUS_THUMB)
        
        embed.set_footer(
            text=f"🐺 Fenrir • From {author.display_name}",
            icon_url=author.avatar.url if author.avatar else EmbedAssets.FENRIR_ICON
        )
        
        return embed


class DashboardEmbed:
    """Embed builders for dashboard displays"""
    
    @staticmethod
    def docker_status(containers: list, running: list, stopped: list) -> discord.Embed:
        """Create a Docker containers status embed"""
        total = len(containers)
        running_pct = (len(running) / total * 100) if total > 0 else 0
        
        # Choose color based on health
        if running_pct >= 95:
            color = 0x44FF44  # Green
        elif running_pct >= 80:
            color = 0xFFAA00  # Orange
        else:
            color = 0xFF4444  # Red
        
        embed = discord.Embed(
            title="🐳 DOCKER STATUS",
            description=(
                f"```\n"
                f"╔══════════════════════════════╗\n"
                f"║  CONTAINER INFRASTRUCTURE    ║\n"
                f"╚══════════════════════════════╝\n"
                f"```\n"
                f"**{len(running)}** / **{total}** containers running\n"
                f"{progress_bar(running_pct)} `{running_pct:.0f}%`"
            ),
            color=color,
            timestamp=datetime.now()
        )
        
        # Running containers
        if running:
            running_text = ""
            for c in running[:12]:
                health = ""
                if "healthy" in c.status.lower():
                    health = " `✓`"
                elif "unhealthy" in c.status.lower():
                    health = " `✗`"
                running_text += f"🟢 {c.display_name}{health}\n"
            
            if len(running) > 12:
                running_text += f"*+{len(running) - 12} more...*"
            
            embed.add_field(
                name=f"▶️ Running ({len(running)})",
                value=running_text or "None",
                inline=True
            )
        
        # Stopped containers
        if stopped:
            stopped_text = "\n".join([f"⏹️ {c.display_name}" for c in stopped[:8]])
            if len(stopped) > 8:
                stopped_text += f"\n*+{len(stopped) - 8} more...*"
            
            embed.add_field(
                name=f"⏸️ Stopped ({len(stopped)})",
                value=stopped_text or "None",
                inline=True
            )
        
        embed.set_thumbnail(url="https://www.docker.com/wp-content/uploads/2022/03/Moby-logo.png")
        embed.set_footer(text="🐺 Fenrir Docker Monitor", icon_url=EmbedAssets.FENRIR_ICON)
        
        return embed
    
    @staticmethod
    def uptimekuma_status(monitors: list, up_count: int, down_count: int) -> discord.Embed:
        """Create an UptimeKuma status embed"""
        total = len(monitors)
        up_pct = (up_count / total * 100) if total > 0 else 0
        
        # Choose color based on status
        if down_count > 0:
            color = 0xFF4444  # Red
            status_text = f"⚠️ **{down_count} SERVICE{'S' if down_count > 1 else ''} DOWN**"
        elif up_pct >= 99:
            color = 0x44FF44  # Green
            status_text = "✅ **ALL SYSTEMS OPERATIONAL**"
        else:
            color = 0xFFAA00  # Orange
            status_text = "⚠️ **PARTIAL OUTAGE**"
        
        embed = discord.Embed(
            title="📊 UPTIME MONITOR",
            description=(
                f"```\n"
                f"╔══════════════════════════════╗\n"
                f"║    SERVICE HEALTH STATUS     ║\n"
                f"╚══════════════════════════════╝\n"
                f"```\n"
                f"{status_text}\n\n"
                f"{progress_bar(up_pct)} `{up_pct:.1f}%`"
            ),
            color=color,
            timestamp=datetime.now()
        )
        
        # Stats row
        embed.add_field(name="🟢 Online", value=f"```\n{up_count}\n```", inline=True)
        embed.add_field(name="🔴 Offline", value=f"```\n{down_count}\n```", inline=True)
        embed.add_field(name="📊 Total", value=f"```\n{total}\n```", inline=True)
        
        embed.set_thumbnail(url="https://uptime.kuma.pet/img/icon.svg")
        embed.set_footer(text="🐺 Fenrir • UptimeKuma Integration", icon_url=EmbedAssets.FENRIR_ICON)
        
        return embed
