"""Discord-facing paths of the docker and dashboard cogs.

Both read the `docker_manager` singleton, replaced here by a fake that never
reaches socket-proxy. The cogs are built with __new__ so DockerCog's
tasks.loop is never started.
"""

import asyncio

import src.cogs.dashboard as dashboard_module
import src.cogs.docker as docker_module
from src.cogs.dashboard import DashboardCog
from src.cogs.docker import DockerCog
from src.utils.docker import ContainerCache, ContainerInfo
from tests.discord_fakes import FakeInteraction, field


def _container(name, state="running", stack="", status="Up 2 hours"):
    return ContainerInfo(id=name[:12], name=name, image=f"{name}:latest",
                         status=status, state=state, stack=stack)


class FakeDockerManager:
    def __init__(self, containers=(), last_updated="2026-10-04T12:00:00"):
        self.containers = list(containers)
        self.cache = ContainerCache(self.containers, last_updated) if containers else None
        self.refreshes = 0

    def get_containers(self, include_stopped=True):
        if include_stopped:
            return self.containers
        return [c for c in self.containers if c.state == "running"]

    def get_container_names(self, include_stopped=True):
        return [c.display_name for c in self.get_containers(include_stopped)]

    def get_stacks(self):
        return sorted({c.stack for c in self.containers if c.stack})

    async def refresh_async(self):
        self.refreshes += 1
        return self.containers


def _docker_cog(monkeypatch, manager):
    monkeypatch.setattr(docker_module, "docker_manager", manager)
    cog = DockerCog.__new__(DockerCog)
    cog.bot = None
    return cog


def _dashboard_cog(monkeypatch, manager):
    monkeypatch.setattr(dashboard_module, "docker_manager", manager)
    cog = DashboardCog.__new__(DashboardCog)
    cog.bot = None
    return cog


# ── /containers ────────────────────────────────────────────────────────────

def test_containers_without_docker_answers_with_an_ephemeral_error(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager())
    inter = FakeInteraction()

    asyncio.run(DockerCog.containers_slash.callback(cog, inter))

    assert inter.log.names() == ["response.send_message"]
    reply = inter.log.of("response.send_message")[0]
    assert reply["content"].startswith("❌")
    assert reply["ephemeral"] is True


def test_containers_lists_running_and_stopped_with_cache_time(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager([
        _container("traefik"), _container("grafana"), _container("old", state="exited"),
    ]))
    inter = FakeInteraction()

    asyncio.run(DockerCog.containers_slash.callback(cog, inter))

    reply = inter.log.of("response.send_message")[0]
    assert reply["ephemeral"] is True
    embed = reply["embed"]
    assert field(embed, "En cours (2)") == "```\ntraefik\ngrafana\n```"
    assert field(embed, "Arrêtés (1)") == "```\nold\n```"
    assert embed.footer.text == "Fenrir · Docker · 2026-10-04T12:00:00"


def test_containers_truncates_each_column_at_fifteen(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager(
        [_container(f"svc{i:02d}") for i in range(17)]
    ))
    inter = FakeInteraction()

    asyncio.run(DockerCog.containers_slash.callback(cog, inter))

    lines = field(inter.log.of("response.send_message")[0]["embed"], "En cours (17)").splitlines()
    assert lines[1:16] == [f"svc{i:02d}" for i in range(15)]
    assert lines[16] == "+2 autres"


# ── /stacks ────────────────────────────────────────────────────────────────

def test_stacks_without_stacks_answers_with_an_ephemeral_error(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager([_container("loose")]))
    inter = FakeInteraction()

    asyncio.run(DockerCog.stacks_slash.callback(cog, inter))

    reply = inter.log.of("response.send_message")[0]
    assert reply["content"].startswith("❌")
    assert reply["ephemeral"] is True


def test_stacks_lists_each_stack_once_sorted(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager([
        _container("traefik", stack="core"), _container("grafana", stack="monitoring"),
        _container("crowdsec", stack="core"),
    ]))
    inter = FakeInteraction()

    asyncio.run(DockerCog.stacks_slash.callback(cog, inter))

    embed = inter.log.of("response.send_message")[0]["embed"]
    assert embed.description == "```\ncore\nmonitoring\n```"


# ── /refresh ───────────────────────────────────────────────────────────────

def test_refresh_defers_before_hitting_docker_then_follows_up_with_counts(monkeypatch):
    manager = FakeDockerManager([
        _container("traefik", stack="core"), _container("grafana", stack="monitoring"),
    ])
    cog = _docker_cog(monkeypatch, manager)
    inter = FakeInteraction()

    asyncio.run(DockerCog.refresh_slash.callback(cog, inter))

    assert manager.refreshes == 1
    assert inter.log.names() == ["response.defer", "followup.send"]
    assert inter.log.of("response.defer")[0] == {"ephemeral": True}
    follow = inter.log.of("followup.send")[0]
    assert follow["content"] == "✅ Rafraîchi ! **2** containers et **2** stacks trouvés"
    assert follow["ephemeral"] is True


# ── autocomplete ───────────────────────────────────────────────────────────

def test_container_autocomplete_filters_case_insensitively_and_caps_at_25(monkeypatch):
    names = [f"app-{i:02d}" for i in range(30)] + ["Traefik"]
    cog = _docker_cog(monkeypatch, FakeDockerManager([_container(n) for n in names]))

    everything = asyncio.run(cog.container_autocomplete(FakeInteraction(), ""))
    filtered = asyncio.run(cog.container_autocomplete(FakeInteraction(), "TRAE"))

    assert len(everything) == 25
    assert [(c.name, c.value) for c in filtered] == [("Traefik", "Traefik")]


def test_stack_autocomplete_filters_by_substring(monkeypatch):
    cog = _docker_cog(monkeypatch, FakeDockerManager([
        _container("a", stack="core"), _container("b", stack="monitoring"),
    ]))

    choices = asyncio.run(cog.stack_autocomplete(FakeInteraction(), "moni"))

    assert [c.value for c in choices] == ["monitoring"]


# ── /dashboard ─────────────────────────────────────────────────────────────

def test_dashboard_defers_publicly_then_reports_docker_unreachable(monkeypatch):
    cog = _dashboard_cog(monkeypatch, FakeDockerManager())
    inter = FakeInteraction()

    asyncio.run(DashboardCog.dashboard_slash.callback(cog, inter))

    assert inter.log.names() == ["response.defer", "followup.send"]
    assert inter.log.of("response.defer")[0] == {}, "the dashboard is posted publicly"
    embed = inter.log.of("followup.send")[0]["embed"]
    assert embed.description == "Aucune donnée disponible · Docker inaccessible"


def test_dashboard_renders_running_and_stopped_columns(monkeypatch):
    cog = _dashboard_cog(monkeypatch, FakeDockerManager([
        _container("traefik", status="Up 2 hours (healthy)"),
        _container("glance", status="Up 1 hour"),
        _container("old", state="exited", status="Exited (0)"),
    ]))
    inter = FakeInteraction()

    asyncio.run(DashboardCog.dashboard_slash.callback(cog, inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert "2/3 en cours" in embed.description
    assert field(embed, "En cours (2)") == "```\ntraefik ok\nglance\n```"
    assert field(embed, "Arrêtés (1)") == "```\nold\n```"


def test_dashboard_flags_an_unhealthy_container_as_err(monkeypatch):
    cog = _dashboard_cog(monkeypatch, FakeDockerManager([
        _container("loki", status="Up 1 hour (unhealthy)"),
    ]))
    inter = FakeInteraction()

    asyncio.run(DashboardCog.dashboard_slash.callback(cog, inter))

    embed = inter.log.of("followup.send")[0]["embed"]
    assert field(embed, "En cours (1)") == "```\nloki err\n```"
