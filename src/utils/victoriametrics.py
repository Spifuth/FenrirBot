"""VictoriaMetrics HTTP client (Prometheus-compatible API)"""

import aiohttp
from datetime import datetime
from typing import Optional


class VictoriaMetricsClient:
    """Async HTTP client for VictoriaMetrics instant and range queries."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def query_instant(self, query: str) -> Optional[float]:
        """Run an instant query and return the first numeric value, or None on error."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/query"
            try:
                async with session.get(url, params={"query": query}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("data", {}).get("result", [])
                    if not results:
                        return None
                    return float(results[0]["value"][1])
            except Exception:
                return None

    async def query_range_stats(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str,
    ) -> Optional[dict]:
        """
        Run a range query and return {"avg": float, "max": float, "min": float}
        computed across all returned data points, or None on error/empty.
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/query_range"
            params = {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step,
            }
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    results = data.get("data", {}).get("result", [])
                    if not results:
                        return None

                    all_values: list[float] = []
                    for series in results:
                        for _ts, val in series.get("values", []):
                            try:
                                all_values.append(float(val))
                            except (ValueError, TypeError):
                                pass

                    if not all_values:
                        return None

                    return {
                        "avg": sum(all_values) / len(all_values),
                        "max": max(all_values),
                        "min": min(all_values),
                    }
            except Exception:
                return None
