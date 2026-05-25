"""Apply a Spec to a discord.Guild. Supports dry_run.

All write operations go through helpers that no-op in dry_run mode and append
a `[DRY]`-prefixed line to the report.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import discord

from .differ import diff_roles
from .models import Spec, RoleSpec
from .permissions import to_permissions
from .reports import Summary
from .resolver import Resolver

log = logging.getLogger("server_config.applier")


@dataclass
class ApplyContext:
    bot: discord.Client
    guild: discord.Guild
    spec: Spec
    resolver: Resolver
    summary: Summary
    dry_run: bool

    def log(self, line: str):
        prefix = "[DRY] " if self.dry_run else ""
        self.summary.detail_lines.append(prefix + line)

    def err(self, line: str):
        self.summary.errors.append(line)


async def apply_roles(ctx: ApplyContext) -> None:
    rd = diff_roles(ctx.guild, ctx.spec.roles)

    # Create
    for spec in rd.to_create:
        ctx.log(f"+ role: {spec.name}")
        if ctx.dry_run:
            ctx.summary.roles_created += 1
            continue
        try:
            role = await ctx.guild.create_role(
                name=spec.name,
                permissions=to_permissions(spec.permissions),
                colour=discord.Colour(int(spec.color.lstrip("#"), 16)),
                hoist=spec.hoist,
                mentionable=spec.mentionable,
                reason="server_config apply",
            )
            ctx.resolver.register_role(spec.id, role)
            ctx.summary.roles_created += 1
        except discord.Forbidden as e:
            ctx.err(f"role create forbidden: {spec.name} ({e})")
        except discord.HTTPException as e:
            ctx.err(f"role create HTTP: {spec.name} ({e})")

    # Edit
    for edit in rd.to_edit:
        ctx.log(f"~ role: {edit.spec.name} ({', '.join(edit.changed_fields)})")
        if ctx.dry_run:
            ctx.summary.roles_edited += 1
            ctx.resolver.register_role(edit.spec.id, edit.role)
            continue
        try:
            await edit.role.edit(
                name=edit.spec.name,
                permissions=to_permissions(edit.spec.permissions),
                colour=discord.Colour(int(edit.spec.color.lstrip("#"), 16)),
                hoist=edit.spec.hoist,
                mentionable=edit.spec.mentionable,
                reason="server_config apply",
            )
            ctx.resolver.register_role(edit.spec.id, edit.role)
            ctx.summary.roles_edited += 1
        except discord.Forbidden as e:
            ctx.err(f"role edit forbidden: {edit.spec.name} ({e})")
        except discord.HTTPException as e:
            ctx.err(f"role edit HTTP: {edit.spec.name} ({e})")

    # Register unchanged for the resolver too
    for spec, role in rd.unchanged:
        ctx.resolver.register_role(spec.id, role)
        ctx.summary.roles_unchanged += 1

    # Reposition: spec order is bottom→top. Skip in dry_run.
    if not ctx.dry_run and (rd.to_create or rd.to_edit):
        try:
            positions: dict[discord.Role, int] = {}
            for i, spec in enumerate(ctx.spec.roles, start=1):
                role = ctx.resolver.roles_by_yaml_id.get(spec.id)
                if role is None or role.managed or role.is_default():
                    continue
                positions[role] = i
            if positions:
                await ctx.guild.edit_role_positions(positions=positions, reason="server_config apply")
        except discord.Forbidden as e:
            ctx.err(f"role reposition forbidden: {e}")
        except discord.HTTPException as e:
            ctx.err(f"role reposition HTTP: {e}")
