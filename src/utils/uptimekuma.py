"""UptimeKuma integration for monitoring status"""

import aiohttp
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

# Optional import for authenticated API
try:
    from uptime_kuma_api import UptimeKumaApi
    HAS_UPTIME_KUMA_API = True
except ImportError:
    HAS_UPTIME_KUMA_API = False
    UptimeKumaApi = None


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
    def from_api(cls, data: dict, uptime_data: Optional[dict] = None) -> "Monitor":
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
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
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


def init_uptimekuma(base_url: str, api_key: Optional[str] = None):
    """Initialize the global UptimeKuma client"""
    global uptimekuma_client
    if base_url:
        uptimekuma_client = UptimeKumaClient(base_url, api_key)
    return uptimekuma_client


class UptimeKumaAuthClient:
    """
    Authenticated client for UptimeKuma using Socket.IO API.
    This allows pause/resume monitors, create maintenances, etc.
    
    Uses uptime-kuma-api library which is synchronous, so we wrap
    calls in a thread pool executor for async compatibility.
    """
    
    def __init__(self, base_url: str, username: str, password: str):
        """
        Initialize authenticated UptimeKuma client
        
        Args:
            base_url: UptimeKuma instance URL (e.g., https://status.example.com)
            username: UptimeKuma username
            password: UptimeKuma password
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._api: Optional[UptimeKumaApi] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._connected = False
        self._monitors_cache: dict[str, int] = {}  # name -> id mapping
    
    def _run_sync(self, func: Callable, *args, **kwargs) -> Any:
        """Run a synchronous function in a thread pool"""
        return func(*args, **kwargs)
    
    async def _run_async(self, func: Callable, *args, **kwargs) -> Any:
        """Run a synchronous function asynchronously using thread pool"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, 
            lambda: func(*args, **kwargs)
        )
    
    async def connect(self) -> bool:
        """
        Connect to UptimeKuma API
        
        Returns:
            True if connected successfully
        """
        if not HAS_UPTIME_KUMA_API:
            print("[UptimeKuma] uptime-kuma-api library not installed. Run: pip install uptime-kuma-api")
            return False
        
        try:
            def _connect():
                self._api = UptimeKumaApi(self.base_url)
                self._api.login(self.username, self.password)
                return True
            
            result = await self._run_async(_connect)
            self._connected = result
            if result:
                print(f"[UptimeKuma] Connected to {self.base_url}")
                await self._refresh_monitors_cache()
            return result
        except Exception as e:
            print(f"[UptimeKuma] Connection failed: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from UptimeKuma API"""
        if self._api:
            try:
                await self._run_async(self._api.disconnect)
            except:
                pass
            self._api = None
            self._connected = False
    
    async def _ensure_connected(self) -> bool:
        """Ensure we're connected, reconnect if necessary"""
        if not self._connected or not self._api:
            return await self.connect()
        return True
    
    async def _refresh_monitors_cache(self):
        """Refresh the monitors name -> id cache"""
        if not await self._ensure_connected():
            return
        
        try:
            def _get_monitors():
                return self._api.get_monitors()
            
            monitors = await self._run_async(_get_monitors)
            self._monitors_cache = {
                m.get("name", "").lower(): m.get("id") 
                for m in monitors
            }
            print(f"[UptimeKuma] Cached {len(self._monitors_cache)} monitors")
        except Exception as e:
            print(f"[UptimeKuma] Error refreshing monitors cache: {e}")
    
    def _find_monitor_id(self, service_name: str) -> Optional[int]:
        """
        Find monitor ID by service name (fuzzy match)
        
        Args:
            service_name: Name of the service/container
            
        Returns:
            Monitor ID if found, None otherwise
        """
        name_lower = service_name.lower()
        
        # Exact match first
        if name_lower in self._monitors_cache:
            return self._monitors_cache[name_lower]
        
        # Partial match (service name contained in monitor name or vice versa)
        for monitor_name, monitor_id in self._monitors_cache.items():
            if name_lower in monitor_name or monitor_name in name_lower:
                return monitor_id
        
        return None
    
    async def get_monitors(self) -> list[dict]:
        """Get all monitors (raw data)"""
        if not await self._ensure_connected():
            return []
        
        try:
            return await self._run_async(self._api.get_monitors)
        except Exception as e:
            print(f"[UptimeKuma] Error getting monitors: {e}")
            return []
    
    async def get_monitors_with_status(self) -> dict:
        """
        Get all monitors with their real status from heartbeats,
        organized by groups.
        
        Returns:
            Dict with 'groups' (dict of group_name -> monitors) and 'ungrouped' (list)
        """
        if not await self._ensure_connected():
            return {"groups": {}, "ungrouped": []}
        
        try:
            def _get_all_data():
                monitors = self._api.get_monitors()
                result = []
                
                for m in monitors:
                    mid = m.get('id')
                    mtype = str(m.get('type', ''))
                    
                    # Skip groups themselves, we only want actual monitors
                    if 'GROUP' in mtype:
                        continue
                    
                    # Get real status from heartbeat
                    try:
                        hb = self._api.get_monitor_beats(mid, 1)
                        if hb:
                            status = hb[-1].get('status', -1)
                        else:
                            status = -1  # No heartbeat
                    except:
                        status = -1
                    
                    result.append({
                        'id': mid,
                        'name': m.get('name', 'Unknown'),
                        'parent': m.get('parent'),
                        'path_name': m.get('pathName', ''),
                        'type': mtype.replace('MonitorType.', ''),
                        'active': m.get('active', True),
                        'status': status,  # 0=down, 1=up, 2=pending, -1=unknown
                        'url': m.get('url', ''),
                        'tags': m.get('tags', [])
                    })
                
                # Build groups dict
                groups_data = {}
                ungrouped = []
                
                # First pass: identify group names
                group_names = {}
                for m in monitors:
                    if 'GROUP' in str(m.get('type', '')):
                        group_names[m.get('id')] = m.get('name', f"Groupe {m.get('id')}")
                
                # Second pass: organize monitors by group
                for mon in result:
                    parent_id = mon.get('parent')
                    if parent_id and parent_id in group_names:
                        group_name = group_names[parent_id]
                        if group_name not in groups_data:
                            groups_data[group_name] = []
                        groups_data[group_name].append(mon)
                    else:
                        ungrouped.append(mon)
                
                return {"groups": groups_data, "ungrouped": ungrouped}
            
            return await self._run_async(_get_all_data)
        except Exception as e:
            print(f"[UptimeKuma] Error getting monitors with status: {e}")
            return {"groups": {}, "ungrouped": []}
    
    async def pause_monitor(self, monitor_id: int) -> bool:
        """
        Pause a monitor by ID
        
        Args:
            monitor_id: The monitor ID to pause
            
        Returns:
            True if successful
        """
        if not await self._ensure_connected():
            return False
        
        try:
            def _pause():
                self._api.pause_monitor(monitor_id)
                return True
            
            result = await self._run_async(_pause)
            print(f"[UptimeKuma] Paused monitor ID {monitor_id}")
            return result
        except Exception as e:
            print(f"[UptimeKuma] Error pausing monitor {monitor_id}: {e}")
            return False
    
    async def resume_monitor(self, monitor_id: int) -> bool:
        """
        Resume a paused monitor by ID
        
        Args:
            monitor_id: The monitor ID to resume
            
        Returns:
            True if successful
        """
        if not await self._ensure_connected():
            return False
        
        try:
            def _resume():
                self._api.resume_monitor(monitor_id)
                return True
            
            result = await self._run_async(_resume)
            print(f"[UptimeKuma] Resumed monitor ID {monitor_id}")
            return result
        except Exception as e:
            print(f"[UptimeKuma] Error resuming monitor {monitor_id}: {e}")
            return False
    
    async def pause_monitor_by_name(self, service_name: str) -> tuple[bool, Optional[int]]:
        """
        Pause a monitor by service/container name
        
        Args:
            service_name: Name of the service to pause monitoring for
            
        Returns:
            Tuple of (success, monitor_id)
        """
        # Refresh cache if empty
        if not self._monitors_cache:
            await self._refresh_monitors_cache()
        
        monitor_id = self._find_monitor_id(service_name)
        if monitor_id is None:
            print(f"[UptimeKuma] No monitor found for service '{service_name}'")
            return False, None
        
        success = await self.pause_monitor(monitor_id)
        return success, monitor_id
    
    async def resume_monitor_by_name(self, service_name: str) -> tuple[bool, Optional[int]]:
        """
        Resume a monitor by service/container name
        
        Args:
            service_name: Name of the service to resume monitoring for
            
        Returns:
            Tuple of (success, monitor_id)
        """
        # Refresh cache if empty
        if not self._monitors_cache:
            await self._refresh_monitors_cache()
        
        monitor_id = self._find_monitor_id(service_name)
        if monitor_id is None:
            print(f"[UptimeKuma] No monitor found for service '{service_name}'")
            return False, None
        
        success = await self.resume_monitor(monitor_id)
        return success, monitor_id
    
    async def get_monitor_status(self, monitor_id: int) -> Optional[dict]:
        """Get status of a specific monitor"""
        if not await self._ensure_connected():
            return None
        
        try:
            monitors = await self._run_async(self._api.get_monitors)
            for m in monitors:
                if m.get("id") == monitor_id:
                    return m
            return None
        except Exception as e:
            print(f"[UptimeKuma] Error getting monitor status: {e}")
            return None


# Global authenticated client instance
uptimekuma_auth_client: Optional[UptimeKumaAuthClient] = None


def init_uptimekuma_auth(base_url: str, username: str, password: str) -> Optional[UptimeKumaAuthClient]:
    """
    Initialize the global authenticated UptimeKuma client
    
    Args:
        base_url: UptimeKuma URL
        username: UptimeKuma username
        password: UptimeKuma password
        
    Returns:
        The client instance if credentials provided, None otherwise
    """
    global uptimekuma_auth_client
    
    if base_url and username and password:
        uptimekuma_auth_client = UptimeKumaAuthClient(base_url, username, password)
        print(f"[UptimeKuma] Auth client initialized for {base_url}")
        return uptimekuma_auth_client
    else:
        print("[UptimeKuma] Auth client not initialized (missing credentials)")
        return None
