"""Docker container discovery and caching"""

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
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    self.cache = ContainerCache.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                self.cache = None

    def _save_cache(self):
        """Save container data to cache file"""
        if self.cache:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(DATA_FILE, "w") as f:
                json.dump(self.cache.to_dict(), f, indent=2)

    def refresh(self) -> list[ContainerInfo]:
        """Refresh container list from Docker daemon"""
        client = self._get_client()
        if client is None:
            return []

        containers = []
        try:
            for c in client.containers.list(all=True):
                image_name = (
                    c.image.tags[0] if c.image.tags
                    else c.attrs.get("Config", {}).get("Image", c.image.short_id)
                )
                containers.append(ContainerInfo(
                    id=c.short_id,
                    name=c.name,
                    image=image_name,
                    status=c.status,
                    state=c.attrs["State"]["Status"],
                ))

            self.cache = ContainerCache(
                containers=containers,
                last_updated=datetime.now().isoformat()
            )
            self._save_cache()

        except Exception as e:
            print(f"⚠️ Docker refresh failed: {e}")

        return containers

    def get_containers(self, include_stopped: bool = True) -> list[ContainerInfo]:
        """Get list of containers (from cache or refresh)"""
        if not self.cache:
            self.refresh()

        if not self.cache:
            return []

        if include_stopped:
            return self.cache.containers
        else:
            return [c for c in self.cache.containers if c.state == "running"]

    def get_container_names(self, include_stopped: bool = True) -> list[str]:
        """Get list of container names for autocomplete"""
        return [c.display_name for c in self.get_containers(include_stopped)]

    def get_stacks(self) -> list[str]:
        """Get unique Docker Compose stack names (from container labels)"""
        client = self._get_client()
        if client is None:
            return []

        stacks = set()
        try:
            for c in client.containers.list(all=True):
                stack = c.labels.get("com.docker.compose.project")
                if stack:
                    stacks.add(stack)
        except Exception as e:
            print(f"⚠️ Docker stacks fetch failed: {e}")

        return sorted(stacks)


# Global instance
docker_manager = DockerManager()
