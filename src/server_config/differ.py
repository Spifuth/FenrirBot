"""Pure diffing logic: Spec items vs current guild objects.

The applier consumes these structured diffs. Keeping the diff pure (no
Discord API calls) lets us unit-test it cleanly and reuse the result for
`/server-config diff` and `dry_run` reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord

from .models import RoleSpec, CategorySpec, ChannelSpec
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


@dataclass
class CategoryDiff:
    to_create: list[CategorySpec] = field(default_factory=list)
    to_edit: list[CategorySpec] = field(default_factory=list)
    unchanged: list[CategorySpec] = field(default_factory=list)


@dataclass
class ChannelDiff:
    to_create: list[tuple[CategorySpec, ChannelSpec]] = field(default_factory=list)
    to_edit: list[tuple[CategorySpec, ChannelSpec]] = field(default_factory=list)
    unchanged: list[tuple[CategorySpec, ChannelSpec]] = field(default_factory=list)


def diff_categories(guild: Any, specs: list[CategorySpec]) -> CategoryDiff:
    result = CategoryDiff()
    by_name = {c.name: c for c in getattr(guild, "categories", [])}
    for spec in specs:
        if spec.name not in by_name:
            result.to_create.append(spec)
        else:
            # Position drift is the only thing we can reasonably check; treat as edit if mismatch.
            existing = by_name[spec.name]
            if getattr(existing, "position", 0) != spec.position:
                result.to_edit.append(spec)
            else:
                result.unchanged.append(spec)
    return result


def diff_channels(guild: Any, categories: list[CategorySpec]) -> ChannelDiff:
    result = ChannelDiff()
    cats_by_name = {c.name: c for c in getattr(guild, "categories", [])}
    for cat_spec in categories:
        parent = cats_by_name.get(cat_spec.name)
        existing_children = list(getattr(parent, "channels", [])) if parent else []
        existing_by_name = {c.name: c for c in existing_children}
        for ch_spec in cat_spec.channels:
            if ch_spec.name not in existing_by_name:
                result.to_create.append((cat_spec, ch_spec))
            else:
                # Conservative: report as unchanged here; the applier will reconcile topic/slowmode.
                result.unchanged.append((cat_spec, ch_spec))
    return result
