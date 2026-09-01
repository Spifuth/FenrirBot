import importlib

import pytest
from discord import app_commands

from src.utils.permissions import admin_only

COGS = [
    "src.cogs.downtime",
    "src.cogs.status",
    "src.cogs.docker",
    "src.cogs.dashboard",
    "src.cogs.reports",
    "src.cogs.alerts",
]

# The only command a non-admin member keeps.
OPEN_COMMANDS = {"ping"}


def _commands_in(module_path):
    module = importlib.import_module(module_path)
    found = []
    for obj in vars(module).values():
        if not isinstance(obj, type):
            continue
        for attr in vars(obj).values():
            if isinstance(attr, app_commands.Command):
                found.append(attr)
    return found


def test_admin_only_sets_both_the_ui_default_and_a_runtime_check():
    @admin_only()
    @app_commands.command(name="probe", description="probe")
    async def probe(interaction):  # pragma: no cover - never invoked
        pass

    assert probe.default_permissions is not None
    assert probe.default_permissions.administrator is True
    assert probe.checks, "a UI default alone is overridable by a guild admin"


@pytest.mark.parametrize("module_path", COGS)
def test_every_command_except_ping_is_guarded(module_path):
    for command in _commands_in(module_path):
        if command.name in OPEN_COMMANDS:
            continue
        assert command.checks, f"/{command.name} has no runtime permission check"
        assert command.default_permissions is not None, f"/{command.name} has no UI default"


def test_ping_stays_open():
    ping = [c for c in _commands_in("src.cogs.status") if c.name == "ping"]
    assert ping, "ping command not found"
    assert not ping[0].checks, "/ping is meant to stay usable by everyone"
