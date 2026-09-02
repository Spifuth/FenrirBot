"""Command permission gates.

`default_permissions` only sets what Discord shows by default — a guild admin
can override it per-command in Server Settings → Integrations. Pairing it with
a real check means the override cannot silently reopen a command.
"""

from discord import app_commands


def admin_only():
    """Require Administrator, both in the Discord UI and at invocation time."""
    def decorator(command):
        command = app_commands.checks.has_permissions(administrator=True)(command)
        command = app_commands.default_permissions(administrator=True)(command)
        return command
    return decorator
