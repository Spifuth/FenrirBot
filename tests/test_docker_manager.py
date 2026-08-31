import json

from src.utils.docker import ContainerCache, ContainerInfo, DockerManager


class FakeSparseContainer:
    """Mimics a docker-py Container returned by list(sparse=True)."""

    def __init__(self, name, image, state, stack):
        self.short_id = "abc123def456"
        self.attrs = {
            "Names": [f"/{name}"],
            "Image": image,
            "State": state,
            "Status": "Up 2 hours" if state == "running" else "Exited (0)",
            "Labels": {"com.docker.compose.project": stack} if stack else {},
        }

    @property
    def name(self):  # docker-py returns None for sparse objects
        return None

    @property
    def labels(self):
        raise Exception("Label data is not available for sparse objects")


class FakeClient:
    def __init__(self, containers):
        self._containers = containers
        self.calls = 0

    class _Collection:
        def __init__(self, outer):
            self.outer = outer

        def list(self, all=False, sparse=False):
            assert sparse is True, "must request a sparse listing to avoid N+1 inspects"
            self.outer.calls += 1
            return self.outer._containers

    @property
    def containers(self):
        return FakeClient._Collection(self)


def _manager(tmp_path, containers):
    mgr = DockerManager.__new__(DockerManager)
    mgr.cache = None
    mgr._client = FakeClient(containers)
    mgr._data_file = tmp_path / "containers.json"
    return mgr


def test_refresh_reads_attrs_not_name_or_labels(tmp_path):
    mgr = _manager(tmp_path, [FakeSparseContainer("traefik", "traefik:v3", "running", "core")])
    out = mgr.refresh()
    assert out[0].name == "traefik"
    assert out[0].image == "traefik:v3"
    assert out[0].state == "running"
    assert out[0].stack == "core"


def test_get_stacks_reads_cache_and_makes_no_api_call(tmp_path):
    mgr = _manager(
        tmp_path,
        [
            FakeSparseContainer("traefik", "traefik:v3", "running", "core"),
            FakeSparseContainer("fenrirbot", "fenrirbot:latest", "running", "management"),
            FakeSparseContainer("orphan", "busybox", "exited", ""),
        ],
    )
    mgr.refresh()
    calls_after_refresh = mgr._client.calls
    assert mgr.get_stacks() == ["core", "management"]
    assert mgr._client.calls == calls_after_refresh, "get_stacks must not hit the API"


def test_cache_survives_a_json_file_without_the_stack_field(tmp_path):
    p = tmp_path / "containers.json"
    p.write_text(json.dumps({
        "containers": [{"id": "a", "name": "old", "image": "i", "status": "s", "state": "running"}],
        "last_updated": "2026-01-01T00:00:00",
    }))
    cache = ContainerCache.from_dict(json.loads(p.read_text()))
    assert cache.containers[0].stack == ""


def test_refresh_keeps_going_when_one_container_vanishes(tmp_path):
    class Vanishing(FakeSparseContainer):
        @property
        def attrs(self):
            raise KeyError("Names")

        @attrs.setter
        def attrs(self, value):
            pass

    good = FakeSparseContainer("traefik", "traefik:v3", "running", "core")
    mgr = _manager(tmp_path, [Vanishing("gone", "x", "running", ""), good])
    out = mgr.refresh()
    assert [c.name for c in out] == ["traefik"]
    assert mgr.cache is not None, "a single bad container must not abandon the whole refresh"
