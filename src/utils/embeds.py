"""Discord embed builders for announcements"""

import discord
import random
from datetime import datetime
from enum import Enum

from .personality import FenrirPersonality


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
    
    # ═══════════════════════════════════════════════════════════════
    # GIF Collections - Random selection for variety
    # ═══════════════════════════════════════════════════════════════
    
    # 🔴 DOWNTIME GIFs - Server crashes, errors, chaos vibes
    DOWNTIME_GIFS = [
        "https://media.giphy.com/media/ZGBQhaRTHyWtRVn1Xx/giphy.gif",  # Server room fire
        "https://media.giphy.com/media/HUkOv6BNWc1HO/giphy.gif",        # This is fine (dog in fire)
        "https://media.giphy.com/media/3o6wrebnKWmvx4ZBio/giphy.gif",   # Glitch effect
        "https://media.giphy.com/media/l1KVaj5UcbHwrBMqI/giphy.gif",    # Computer smash
        "https://media.giphy.com/media/xTiTnrliW65rlwud8I/giphy.gif",   # Alert sirens
        "https://media.giphy.com/media/3oEjI8vagntG7EDxgQ/giphy.gif",   # Matrix glitch
        "https://media.giphy.com/media/QMHoU66sBXqqLqYvGO/giphy.gif",   # Windows error
        "https://media.giphy.com/media/j3DxBrKsR7zxB2dKKe/giphy.gif",   # Explosion
        "https://media.giphy.com/media/3o7TKwmnDgQb5jemjK/giphy.gif",   # Server rack panic
        "https://media.giphy.com/media/hv5AEBpH3ZyNoRnABG/giphy.gif",   # 404 glitch
    ]
    
    # 🟢 RESTORED GIFs - Success, celebration, back online vibes
    RESTORED_GIFS = [
        "https://media.giphy.com/media/3ohzdIuqJoo8QdKlnW/giphy.gif",   # Thumbs up kid
        "https://media.giphy.com/media/a0h7sAqON67nO/giphy.gif",        # Success kid
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",    # Celebration
        "https://media.giphy.com/media/xT0GqssRweIhlz209i/giphy.gif",   # Success confetti
        "https://media.giphy.com/media/XreQmk7ETCak0/giphy.gif",        # Clapping
        "https://media.giphy.com/media/l0MYC0LajbaPoEADu/giphy.gif",    # We did it!
        "https://media.giphy.com/media/artj92V8o75VPL7AeQ/giphy.gif",   # Gg ez
        "https://media.giphy.com/media/fdyZ3qI0GVZC0/giphy.gif",        # Minions cheering
        "https://media.giphy.com/media/3o6fJ1BM7R2EBRDnxK/giphy.gif",   # Green light
        "https://media.giphy.com/media/l3V0j3ytFyGHqiV7W/giphy.gif",    # Mission complete
    ]
    
    # 🟡 SCHEDULED GIFs - Maintenance, planning, work in progress
    SCHEDULED_GIFS = [
        "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",    # Clock countdown
        "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",   # Calendar flip
        "https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif",        # Typing cat
        "https://media.giphy.com/media/LmNwrBhejkK9EFP504/giphy.gif",   # Work in progress
        "https://media.giphy.com/media/xTiTnxpQ3ghPiB2Hp6/giphy.gif",   # Construction
        "https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.gif",   # Gears turning
        "https://media.giphy.com/media/l4FGuhL4U2WyjdkaY/giphy.gif",    # Wrench tools
        "https://media.giphy.com/media/SVCSsoKU5v6ZJLk07n/giphy.gif",   # Loading
        "https://media.giphy.com/media/3oKIPnAiaMCws8nOsE/giphy.gif",   # Hacker coding
        "https://media.giphy.com/media/Dh5q0sShxgp13DwrvG/giphy.gif",   # Maintenance bot
    ]
    
    # ═══════════════════════════════════════════════════════════════
    # Thumbnails (top-right icons) - Twemoji for reliability
    # ═══════════════════════════════════════════════════════════════
    DOWNTIME_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f6a8.png"   # 🚨
    RESTORED_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/2705.png"    # ✅
    SCHEDULED_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4c5.png"  # 📅
    STATUS_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/2139.png"      # ℹ️
    DASHBOARD_THUMB = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4ca.png"  # 📊
    FENRIR_ICON = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f43a.png"      # 🐺
    
    @classmethod
    def random_downtime_gif(cls) -> str:
        """Get a random downtime GIF"""
        return random.choice(cls.DOWNTIME_GIFS)
    
    @classmethod
    def random_restored_gif(cls) -> str:
        """Get a random restored GIF"""
        return random.choice(cls.RESTORED_GIFS)
    
    @classmethod
    def random_scheduled_gif(cls) -> str:
        """Get a random scheduled GIF"""
        return random.choice(cls.SCHEDULED_GIFS)


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
        personality = FenrirPersonality()
        greeting = personality.get_greeting()
        mood_emoji = personality.get_mood_emoji()
        quip = personality.get_footer_quip()
        
        embed = discord.Embed(
            title=f"{mood_emoji} DOWNTIME ALERT",
            description=(
                f"```ansi\n"
                f"\u001b[1;31m█▀▀ █▀▀ █▀█ █░█ █ █▀▀ █▀▀   █▀▄ █▀█ █░█░█ █▄░█\n"
                f"\u001b[1;31m▄▄█ ██▄ █▀▄ ▀▄▀ █ █▄▄ ██▄   █▄▀ █▄█ ▀▄▀▄▀ █░▀█\n"
                f"```\n"
                f"*{greeting}*\n\n"
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
        embed.set_image(url=EmbedAssets.random_downtime_gif())
        
        # Footer with author and mood quip
        embed.set_footer(
            text=f"🐺 Fenrir {quip} • Announced by {author.display_name}",
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
        personality = FenrirPersonality()
        restored_msg = personality.get_restored_message()
        mood_emoji = personality.get_mood_emoji()
        quip = personality.get_footer_quip()
        
        embed = discord.Embed(
            title=f"{mood_emoji} SERVICE RESTORED",
            description=(
                f"```ansi\n"
                f"\u001b[1;32m█▀▀ █▀▀ █▀█ █░█ █ █▀▀ █▀▀   █░█ █▀█\n"
                f"\u001b[1;32m▄▄█ ██▄ █▀▄ ▀▄▀ █ █▄▄ ██▄   █▄█ █▀▀\n"
                f"```\n"
                f"*{restored_msg}*\n\n"
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
        embed.set_image(url=EmbedAssets.random_restored_gif())
        
        embed.set_footer(
            text=f"🐺 Fenrir {quip} • Restored by {author.display_name}",
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
        personality = FenrirPersonality()
        scheduled_msg = personality.get_scheduled_message()
        mood_emoji = personality.get_mood_emoji()
        quip = personality.get_footer_quip()
        
        embed = discord.Embed(
            title=f"{mood_emoji} SCHEDULED MAINTENANCE",
            description=(
                f"```ansi\n"
                f"\u001b[1;33m█▀█ █░░ ▄▀█ █▄░█ █▄░█ █▀▀ █▀▄\n"
                f"\u001b[1;33m█▀▀ █▄▄ █▀█ █░▀█ █░▀█ ██▄ █▄▀\n"
                f"```\n"
                f"*{scheduled_msg}*\n\n"
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
        embed.set_image(url=EmbedAssets.random_scheduled_gif())
        
        embed.set_footer(
            text=f"🐺 Fenrir {quip} • Scheduled by {author.display_name}",
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
