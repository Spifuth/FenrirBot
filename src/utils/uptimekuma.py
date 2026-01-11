"""UptimeKuma integration for monitoring status"""

import aiohttp
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class MonitorStatus(Enum):
    """UptimeKuma monitor status codes"""
    DOWN = 0
    UP = 1
    PENDING = 2
    MAINTENANCE = 3
    
    @property
    def emoji(self) -> str:
        return {
            MonitorStatus.DOWN: "🔴",
            MonitorStatus.UP: "🟢",
            MonitorStatus.PENDING: "🟡",
            MonitorStatus.MAINTENANCE: "🔧"
        }.get(self, "⚪")
    
    @property
    def label(self) -> str:
        return {
            MonitorStatus.DOWN: "Down",
            MonitorStatus.UP: "Up",
            MonitorStatus.PENDING: "Pending",
            MonitorStatus.MAINTENANCE: "Maintenance"
        }.get(self, "Unknown")


@dataclass
class Monitor:
    """UptimeKuma monitor info"""
    id: int
    name: str
    status: MonitorStatus
    uptime_24h: float = 0.0
    uptime_30d: float = 0.0
    response_time: int = 0  # ms
    url: Optional[str] = None
    
    @classmethod
    def from_api(cls, data: dict, uptime_data: dict = None) -> "Monitor":
        """Create Monitor from UptimeKuma API response"""
        status_code = data.get("status", 2)
        try:
            status = MonitorStatus(status_code)
        except ValueError:
            status = MonitorStatus.PENDING
        
        uptime_24h = 0.0
        uptime_30d = 0.0
        
        if uptime_data:
            # UptimeKuma returns uptime as percentage
            uptime_24h = uptime_data.get("24", 0.0) * 100 if uptime_data.get("24") else 0.0
            uptime_30d = uptime_data.get("720", 0.0) * 100 if uptime_data.get("720") else 0.0
        
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "Unknown"),
            status=status,
            uptime_24h=uptime_24h,
            uptime_30d=uptime_30d,
            response_time=data.get("avgPing", 0) or 0,
            url=data.get("url")
        )


class UptimeKumaClient:
    """Client for UptimeKuma API"""
    
    def __init__(self, base_url: str, api_key: str = None):
        """
        Initialize UptimeKuma client
        
        Args:
            base_url: UptimeKuma instance URL (e.g., https://status.example.com)
            api_key: Optional API key for authenticated access
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_status_page(self, slug: str = "default") -> dict:
        """
        Get public status page data (no auth required if page is public)
        
        Args:
            slug: Status page slug (default: "default")
        
        Returns:
            Status page data with monitors
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/api/status-page/{slug}") as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except aiohttp.ClientError as e:
            return {"error": str(e)}
    
    async def get_heartbeats(self, slug: str = "default") -> dict:
        """
        Get heartbeat/uptime data for status page monitors
        
        Args:
            slug: Status page slug
            
        Returns:
            Heartbeat data including uptime percentages
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/api/status-page/heartbeat/{slug}") as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return {"error": f"HTTP {resp.status}"}
        except aiohttp.ClientError as e:
            return {"error": str(e)}
    
    async def get_monitors(self, slug: str = "default") -> list[Monitor]:
        """
        Get all monitors from a status page with their current status
        
        Args:
            slug: Status page slug
            
        Returns:
            List of Monitor objects
        """
        # Get status page config
        status_data = await self.get_status_page(slug)
        if "error" in status_data:
            return []
        
        # Get heartbeat data
        heartbeat_data = await self.get_heartbeats(slug)
        
        monitors = []
        
        # Parse heartbeat data for current status
        heartbeat_list = heartbeat_data.get("heartbeatList", {})
        uptime_list = heartbeat_data.get("uptimeList", {})
        
        for monitor_id, heartbeats in heartbeat_list.items():
            if heartbeats:
                # Get latest heartbeat
                latest = heartbeats[-1] if heartbeats else {}
                
                # Find monitor name from status page
                monitor_name = f"Monitor {monitor_id}"
                for group in status_data.get("publicGroupList", []):
                    for m in group.get("monitorList", []):
                        if str(m.get("id")) == str(monitor_id):
                            monitor_name = m.get("name", monitor_name)
                            break
                
                # Get uptime data
                uptime_data = uptime_list.get(str(monitor_id), {})
                
                monitor = Monitor(
                    id=int(monitor_id),
                    name=monitor_name,
                    status=MonitorStatus(latest.get("status", 2)),
                    uptime_24h=uptime_data.get("24", 0) * 100 if uptime_data.get("24") else 0,
                    uptime_30d=uptime_data.get("720", 0) * 100 if uptime_data.get("720") else 0,
                    response_time=latest.get("ping", 0) or 0
                )
                monitors.append(monitor)
        
        return monitors
    
    async def check_status(self) -> bool:
        """Check if UptimeKuma is reachable"""
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/api/status-page/default", timeout=5) as resp:
                return resp.status in [200, 404]  # 404 is ok, means API works but no default page
        except:
            return False


# Global client instance (initialized from config)
uptimekuma_client: Optional[UptimeKumaClient] = None


def init_uptimekuma(base_url: str, api_key: str = None):
    """Initialize the global UptimeKuma client"""
    global uptimekuma_client
    if base_url:
        uptimekuma_client = UptimeKumaClient(base_url, api_key)
    return uptimekuma_client
