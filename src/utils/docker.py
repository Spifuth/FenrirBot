"""Docker container discovery and caching"""

import asyncio
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

try:
    import docker
    HAS_DOCKER_SDK = True
except ImportError:
    HAS_DOCKER_SDK = False


DATA_FILE = Path(__file__).parent.parent.parent / "data" / "containers.json"


@dataclass
class ContainerInfo:
    """Container information"""
    id: str
    name: str
    image: str
    status: str
    state: str  # running, exited, paused, etc.
    stack: str = ""  # com.docker.compose.project label, "" if not composed

    @property
    def display_name(self) -> str:
        """Friendly display name for Discord"""
        return self.name.lstrip("/")


@dataclass
class ContainerCache:
    """Cached container data"""
    containers: list[ContainerInfo]
    last_updated: str

    def to_dict(self) -> dict:
        return {
            "containers": [asdict(c) for c in self.containers],
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContainerCache":
        containers = [ContainerInfo(**c) for c in data.get("containers", [])]
        return cls(containers=containers, last_updated=data.get("last_updated", ""))


class DockerManager:
    """Manages Docker container discovery and caching via docker-py SDK"""

    def __init__(self):
        self.cache: Optional[ContainerCache] = None
        self._client: Optional["docker.DockerClient"] = None
        self._data_file = DATA_FILE
        self._load_cache()

    def _get_client(self) -> Optional["docker.DockerClient"]:
        """Lazily initialize the Docker client (reads DOCKER_HOST env var)"""
        if not HAS_DOCKER_SDK:
            print("⚠️ docker-py not installed. Run: pip install docker")
            return None
        if self._client is None:
            try:
                self._client = docker.from_env()
            except Exception as e:
                print(f"⚠️ Docker client unavailable: {e}")
                return None
        return self._client

    def _load_cache(self):
        """Load cached container data from file"""
        if self._data_file.exists():
            try:
                with open(self._data_file, "r") as f:
                    data = json.load(f)
                    self.cache = ContainerCache.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError):
                self.cache = None

    def _save_cache(self):
        """Save container data to cache file (atomic: write temp, then replace)"""
        if not self.cache:
            return
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._data_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.cache.to_dict(), f, indent=2)
        tmp.replace(self._data_file)

    def refresh(self) -> list[ContainerInfo]:
        """Refresh container list from the Docker daemon.

        Uses sparse=True: one API call instead of 1+N inspects, and immune to a
        container being removed mid-iteration. Sparse objects do NOT populate
        `.name` (returns None) or `.labels` (raises), so read `.attrs` directly.
        """
        client = self._get_client()
        if client is None:
            return []

        try:
            raw = client.containers.list(all=True, sparse=True)
        except Exception as e:
            print(f"⚠️ Docker refresh failed: {e}")
            return []

        containers = []
        for c in raw:
            try:
                attrs = c.attrs
                names = attrs.get("Names") or []
                name = names[0].lstrip("/") if names else attrs.get("Id", "")[:12]
                containers.append(ContainerInfo(
                    id=c.short_id,
                    name=name,
                    image=attrs.get("Image", ""),
                    status=attrs.get("Status", ""),
                    state=attrs.get("State", ""),
                    stack=(attrs.get("Labels") or {}).get("com.docker.compose.project", ""),
                ))
            except Exception as e:
                # One malformed or vanished entry must not abandon the whole refresh.
                print(f"⚠️ Skipping a container during refresh: {e!r}")
                continue

        self.cache = ContainerCache(
            containers=containers,
            last_updated=datetime.now().isoformat()
        )
        # Persistence is a nicety; the in-memory cache is what the cogs read.
        # This call is reached from a tasks.loop's before_loop, so letting it
        # raise would stop the loop from ever starting and leave /containers,
        # /stacks, /dashboard and every autocomplete silently empty. A
        # read-only /app/data (a bind mount whose ownership was not updated
        # for the non-root user) is exactly how that happens.
        try:
            self._save_cache()
        except OSError as e:
            print(f"⚠️ Could not persist the container cache: {e!r}")
        return containers

    async def refresh_async(self) -> list[ContainerInfo]:
        """Run the blocking refresh off the event loop."""
        return await asyncio.to_thread(self.refresh)

    def get_containers(self, include_stopped: bool = True) -> list[ContainerInfo]:
        """Get list of containers from cache. Never blocks; never calls the API."""
        if not self.cache:
            return []

        if include_stopped:
            return self.cache.containers
        return [c for c in self.cache.containers if c.state == "running"]

    def get_container_names(self, include_stopped: bool = True) -> list[str]:
        """Get list of container names for autocomplete"""
        return [c.display_name for c in self.get_containers(include_stopped)]

    def get_stacks(self) -> list[str]:
        """Unique Compose stack names, read from the cache. No API call."""
        return sorted({c.stack for c in self.get_containers(True) if c.stack})


# Global instance
docker_manager = DockerManager()
