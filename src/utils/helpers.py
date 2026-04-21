"""Shared utilities and helpers for all cogs"""

import discord
from typing import Optional
from datetime import datetime, timedelta, timezone

from ..config import config


# ═══════════════════════════════════════════════════════════════════════════════
# Timezone Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Paris timezone (CET/CEST)
try:
    from zoneinfo import ZoneInfo
    PARIS_TZ = ZoneInfo("Europe/Paris")
except ImportError:
    # Fallback for Python < 3.9
    PARIS_TZ = timezone(timedelta(hours=1))


# ═══════════════════════════════════════════════════════════════════════════════
# Channel & Mention Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def get_announcement_channel(bot: discord.Client, fallback: Optional[discord.abc.Messageable] = None) -> Optional[discord.abc.Messageable]:
    """Get the configured announcement channel or fall back to provided channel"""
    if config and config.announcement_channel_id:
        channel = bot.get_channel(config.announcement_channel_id)
        if channel:
            return channel
    return fallback


def get_notification_mention() -> str:
    """Get the role mention string or fall back to @here"""
    if config and config.notification_role_id:
        return f"<@&{config.notification_role_id}>"
    return "@here"


# ═══════════════════════════════════════════════════════════════════════════════
# Progress Bars & Visual Helpers
# ═══════════════════════════════════════════════════════════════════════════════

# Standard thresholds used across all cogs
THRESHOLDS = {
    "cpu": {"warning": 80, "critical": 95},
    "ram": {"warning": 85, "critical": 95},
    "memory": {"warning": 85, "critical": 95},
    "disk": {"warning": 80, "critical": 90},
    "swap": {"warning": 50, "critical": 80},
    "temp": {"warning": 70, "critical": 85},
    "temperature": {"warning": 70, "critical": 85},
    "network": {"warning": 80, "critical": 95},
    "load": {"warning": 75, "critical": 90},
    "generic": {"warning": 75, "critical": 90},
}


def get_thresholds(metric_type: str) -> tuple[int, int]:
    """Get warning and critical thresholds for a metric type"""
    metric_lower = metric_type.lower()
    
    for key, thresh in THRESHOLDS.items():
        if key in metric_lower:
            return (thresh["warning"], thresh["critical"])
    
    return (THRESHOLDS["generic"]["warning"], THRESHOLDS["generic"]["critical"])


def create_progress_bar(
    value: float, 
    metric_type: str = "generic",
    show_percentage: bool = True,
    bar_length: int = 10
) -> str:
    """
    Create a visual progress bar for a metric.
    
    Args:
        value: Current value (0-100 for percentages)
        metric_type: Type of metric for threshold coloring
        show_percentage: Whether to show the percentage value
        bar_length: Number of segments in the bar
    
    Returns:
        Formatted progress bar string
    """
    warn_threshold, crit_threshold = get_thresholds(metric_type)
    
    # Clamp value to valid range
    value = max(0, min(100, value))
    
    # Determine color based on thresholds
    if value >= crit_threshold:
        bar_char = "🟥"
    elif value >= warn_threshold:
        bar_char = "🟨"
    else:
        bar_char = "🟩"
    
    # Create the bar
    filled = min(int(value / (100 / bar_length)), bar_length)
    empty = bar_length - filled
    bar = bar_char * filled + "⬜" * empty
    
    if show_percentage:
        return f"{bar} **{value:.1f}%**"
    return bar


def get_metric_emoji(metric_name: str) -> str:
    """Get an appropriate emoji for a metric type"""
    metric_lower = metric_name.lower()
    
    emoji_map = {
        "cpu": "🖥️",
        "memory": "🧠",
        "ram": "🧠",
        "disk": "💾",
        "storage": "💾",
        "network": "🌐",
        "bandwidth": "🌐",
        "traffic": "🌐",
        "temp": "🌡️",
        "temperature": "🌡️",
        "load": "📊",
        "io": "💿",
        "swap": "🔄",
        "uptime": "⏱️",
    }
    
    for key, emoji in emoji_map.items():
        if key in metric_lower:
            return emoji
    
    return "📈"


def get_status_color(status: str) -> int:
    """Get Discord color for a status string"""
    status_lower = status.lower()
    
    colors = {
        "critical": 0xFF0000,
        "error": 0xFF0000,
        "down": 0xFF0000,
        "warning": 0xFFAA00,
        "warn": 0xFFAA00,
        "pending": 0xFFAA00,
        "clear": 0x44FF44,
        "ok": 0x44FF44,
        "up": 0x44FF44,
        "success": 0x44FF44,
        "info": 0x5865F2,
        "maintenance": 0x5865F2,
        "unknown": 0x808080,
        "undefined": 0x808080,
    }
    
    for key, color in colors.items():
        if key in status_lower:
            return color
    
    return 0x808080


def get_status_emoji(status: str) -> str:
    """Get emoji for a status string"""
    status_lower = status.lower()
    
    emojis = {
        "critical": "🚨",
        "error": "❌",
        "down": "🔴",
        "warning": "⚠️",
        "warn": "⚠️",
        "pending": "🟡",
        "clear": "✅",
        "ok": "✅",
        "up": "🟢",
        "success": "✅",
        "info": "ℹ️",
        "maintenance": "🔧",
        "unknown": "❓",
        "undefined": "❓",
    }
    
    for key, emoji in emojis.items():
        if key in status_lower:
            return emoji
    
    return "❓"


# ═══════════════════════════════════════════════════════════════════════════════
# Time & Duration Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string"""
    if seconds < 0:
        return "N/A"
    
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts) if parts else "0s"


def format_uptime(seconds: int) -> str:
    """Format uptime in a compact way"""
    return format_duration(seconds)


def format_timestamp(dt: datetime, style: str = "relative") -> str:
    """
    Format a datetime for Discord display.
    
    Styles: 
        - relative: "2 hours ago"
        - short: "12/01/2026 10:30"
        - long: "12 January 2026 at 10:30"
    """
    if style == "relative":
        return f"<t:{int(dt.timestamp())}:R>"
    elif style == "short":
        return f"<t:{int(dt.timestamp())}:f>"
    elif style == "long":
        return f"<t:{int(dt.timestamp())}:F>"
    else:
        return dt.strftime("%d/%m/%Y %H:%M")


# ═══════════════════════════════════════════════════════════════════════════════
# Error Handling Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def create_error_embed(
    title: str = "Erreur",
    description: str = "Une erreur est survenue.",
    error: Exception | None = None,
) -> discord.Embed:
    """Create a standardized error embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )
    if error:
        embed.add_field(name="Détails", value=f"```\n{str(error)[:200]}\n```", inline=False)
    embed.set_footer(text="Fenrir")
    return embed


def create_success_embed(
    title: str = "Succès",
    description: str = "Opération réussie.",
) -> discord.Embed:
    """Create a standardized success embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )


def create_info_embed(
    title: str,
    description: str = "",
) -> discord.Embed:
    """Create a standardized info embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0x2C2F33,
        timestamp=datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Config Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def get_config_value(key: str, default=None):
    """Safely get a config value"""
    if config:
        return getattr(config, key, default)
    return default




def is_webhook_enabled() -> bool:
    """Check if webhook server is enabled"""
    return get_config_value('webhook_enabled', False)
