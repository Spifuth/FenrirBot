"""Pure diffing logic: Spec items vs current guild objects.

The applier consumes these structured diffs. Keeping the diff pure (no
Discord API calls) lets us unit-test it cleanly and reuse the result for
`/server-config diff` and `dry_run` reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord

from .models import RoleSpec
from .permissions import to_permissions


@dataclass
class RoleEdit:
    role: Any  # discord.Role
    spec: RoleSpec
    changed_fields: list[str] = field(default_factory=list)


@dataclass
class RoleDiff:
    to_create: list[RoleSpec] = field(default_factory=list)
    to_edit: list[RoleEdit] = field(default_factory=list)
    unchanged: list[tuple[RoleSpec, Any]] = field(default_factory=list)


def diff_roles(guild: Any, specs: list[RoleSpec]) -> RoleDiff:
    """Compare spec roles against guild.roles (by name)."""
    result = RoleDiff()
    by_name = {r.name: r for r in guild.roles}

    for spec in specs:
        existing = by_name.get(spec.name)
        if existing is None:
            result.to_create.append(spec)
            continue

        changed = []
        spec_color = int(spec.color.lstrip("#"), 16)
        if getattr(existing.color, "value", 0) != spec_color:
            changed.append("color")
        if getattr(existing, "hoist", False) != spec.hoist:
            changed.append("hoist")
        if getattr(existing, "mentionable", False) != spec.mentionable:
            changed.append("mentionable")

        spec_perm_value = to_permissions(spec.permissions).value
        if getattr(existing.permissions, "value", 0) != spec_perm_value:
            changed.append("permissions")

        if changed:
            result.to_edit.append(RoleEdit(role=existing, spec=spec, changed_fields=changed))
        else:
            result.unchanged.append((spec, existing))

    return result
