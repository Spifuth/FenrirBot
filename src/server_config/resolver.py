"""Cache YAML id -> discord object lookups.

Names are the matching key on Discord (we cannot store Discord ids in the spec
because the spec is portable between guilds). Idempotency contract:
- roles: matched by name (must be unique within the spec)
- categories: matched by name
- channels: matched by name + parent category name
"""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

from .models import Spec


@dataclass
class Resolver:
    guild: discord.Guild
    spec: Spec
    roles_by_yaml_id: dict[str, discord.Role] = field(default_factory=dict)
    categories_by_yaml_id: dict[str, discord.CategoryChannel] = field(default_factory=dict)
    channels_by_yaml_id: dict[str, discord.abc.GuildChannel] = field(default_factory=dict)

    def register_role(self, yaml_id: str, role: discord.Role) -> None:
        self.roles_by_yaml_id[yaml_id] = role

    def register_category(self, yaml_id: str, cat: discord.CategoryChannel) -> None:
        self.categories_by_yaml_id[yaml_id] = cat

    def register_channel(self, yaml_id: str, ch: discord.abc.GuildChannel) -> None:
        self.channels_by_yaml_id[yaml_id] = ch

    def resolve_target(self, target: str) -> discord.Role | discord.Member | None:
        """Resolve an overwrite target ('@everyone' or a YAML role id)."""
        if target == "@everyone":
            return self.guild.default_role
        return self.roles_by_yaml_id.get(target)

    def find_existing_role_by_name(self, name: str) -> discord.Role | None:
        return discord.utils.get(self.guild.roles, name=name)

    def find_existing_category_by_name(self, name: str) -> discord.CategoryChannel | None:
        return discord.utils.get(self.guild.categories, name=name)

    def find_existing_channel(
        self, name: str, parent: discord.CategoryChannel | None
    ) -> discord.abc.GuildChannel | None:
        for ch in self.guild.channels:
            if ch.name == name and getattr(ch, "category_id", None) == (parent.id if parent else None):
                return ch
        return None
