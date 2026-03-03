"""Docker container discovery and caching"""

import json
import subprocess
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


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
    """Manages Docker container discovery and caching"""
    
    def __init__(self):
        self.cache: Optional[ContainerCache] = None
        self._load_cache()
    
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
        containers = []
        
        try:
            # Get all containers (running and stopped)
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.State}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("|")
                        if len(parts) >= 5:
                            containers.append(ContainerInfo(
                                id=parts[0],
                                name=parts[1],
                                image=parts[2],
                                status=parts[3],
                                state=parts[4]
                            ))
            
            self.cache = ContainerCache(
                containers=containers,
                last_updated=datetime.now().isoformat()
            )
            self._save_cache()
            
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"⚠️ Docker not available: {e}")
        
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
        stacks = set()
        
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Labels}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    # Look for com.docker.compose.project label
                    for label in line.split(","):
                        if "com.docker.compose.project=" in label:
                            stack_name = label.split("=")[1]
                            stacks.add(stack_name)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return sorted(list(stacks))


# Global instance
docker_manager = DockerManager()
