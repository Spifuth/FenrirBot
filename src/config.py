"""Bot configuration management"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file immediately when this module is imported
load_dotenv()


@dataclass
class Config:
    """Bot configuration container"""
    token: str
    announcement_channel_id: int
    notification_role_id: int = 0
    command_prefix: str = "!"
    uptimekuma_url: str = ""
    uptimekuma_api_key: str = ""
    uptimekuma_status_page: str = "default"
    # Uptime Kuma authenticated API (for pause/resume monitors)
    uptimekuma_username: str = ""
    uptimekuma_password: str = ""
    uptimekuma_auto_pause: bool = True  # Auto-pause monitors during maintenance
    # Webhook server settings
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8085
    webhook_secret: str = ""
    # Netdata settings
    netdata_url: str = ""
    netdata_api_key: str = ""
    # Reports settings
    reports_channel_id: int = 0
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in environment variables")
        
        channel_id = os.getenv("ANNOUNCEMENT_CHANNEL_ID", "0")
        role_id = os.getenv("NOTIFICATION_ROLE_ID", "0")
        
        return cls(
            token=token,
            announcement_channel_id=int(channel_id),
            notification_role_id=int(role_id),
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
            uptimekuma_url=os.getenv("UPTIMEKUMA_URL", ""),
            uptimekuma_api_key=os.getenv("UPTIMEKUMA_API_KEY", ""),
            uptimekuma_status_page=os.getenv("UPTIMEKUMA_STATUS_PAGE", "default"),
            uptimekuma_username=os.getenv("UPTIMEKUMA_USERNAME", ""),
            uptimekuma_password=os.getenv("UPTIMEKUMA_PASSWORD", ""),
            uptimekuma_auto_pause=os.getenv("UPTIMEKUMA_AUTO_PAUSE", "true").lower() == "true",
            webhook_enabled=os.getenv("WEBHOOK_ENABLED", "false").lower() == "true",
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=int(os.getenv("WEBHOOK_PORT", "8085")),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            netdata_url=os.getenv("NETDATA_URL", ""),
            netdata_api_key=os.getenv("NETDATA_API_KEY", ""),
            reports_channel_id=int(os.getenv("REPORTS_CHANNEL_ID", "0"))
        )


config = Config.from_env() if os.getenv("DISCORD_TOKEN") else None
