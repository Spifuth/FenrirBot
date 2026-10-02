"""Bot configuration management"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot configuration container"""
    token: str
    announcement_channel_id: int
    notification_role_id: int = 0
    command_prefix: str = "!"
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8085
    webhook_secret: str = ""
    victoriametrics_url: str = ""
    reports_channel_id: int = 0
    grafana_url: str = ""
    grafana_api_key: str = ""

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
            webhook_enabled=os.getenv("WEBHOOK_ENABLED", "false").lower() == "true",
            webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=int(os.getenv("WEBHOOK_PORT", "8085")),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            victoriametrics_url=os.getenv("VICTORIAMETRICS_URL", ""),
            reports_channel_id=int(os.getenv("REPORTS_CHANNEL_ID", "0")),
            grafana_url=os.getenv("GRAFANA_URL", ""),
            grafana_api_key=os.getenv("GRAFANA_API_KEY", ""),
        )


config = Config.from_env() if os.getenv("DISCORD_TOKEN") else None
