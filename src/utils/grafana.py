"""Grafana REST API client"""

import aiohttp


class GrafanaClient:
    """Async HTTP client for the Grafana REST API."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def get_active_alerts(self) -> list[dict] | None:
        """
        Fetch currently firing alerts from Grafana Alertmanager.

        Returns the alert list on success (possibly empty), or **None** if the
        result could not be determined — a dead API or a rejected token must
        never render as "no alerts", which is an all-clear the caller cannot
        distinguish from a real one.
        """
        url = f"{self.base_url}/api/alertmanager/grafana/api/v2/alerts"
        params = {"active": "true", "silenced": "false", "inhibited": "false"}
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        print(f"⚠️ Grafana returned {resp.status} for {url}")
                        return None
                    return await resp.json()
        except Exception as e:
            print(f"⚠️ Grafana unreachable: {e!r}")
            return None

    async def health_check(self) -> bool:
        """Returns True if Grafana API is reachable and authenticated."""
        url = f"{self.base_url}/api/health"
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False
