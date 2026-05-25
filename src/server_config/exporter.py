"""Export the current guild state to a YAML spec.

This is best-effort: we use canonical YAML ids derived from current names
(slugified). The output is a valid spec but loses comments. Re-importing
it will produce an idempotent apply.
"""

from __future__ import annotations

import io
import re

import discord
from ruamel.yaml import YAML

from .permissions import PERM_MAP


_INVERSE_PERM_MAP = {v: k for k, v in PERM_MAP.items()}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "x"


def _perms_to_names(perms: discord.Permissions) -> list[str]:
    names = []
    for attr, value in perms:
        if value and attr in _INVERSE_PERM_MAP:
            names.append(_INVERSE_PERM_MAP[attr])
    return names


def export_guild(guild: discord.Guild) -> str:
    """Return a YAML string representing the guild's current state."""
    data = {
        "meta": {"spec_version": "1.0", "description": f"Exported from {guild.name}"},
        "server": {
            "name": guild.name,
            "verification_level": guild.verification_level.name.upper(),
            "explicit_content_filter": guild.explicit_content_filter.name.upper(),
            "default_notifications": guild.default_notifications.name.upper(),
            "community_enabled": "COMMUNITY" in guild.features,
        },
        "roles": [],
        "categories": [],
        "webhooks": [],
        "reaction_roles": [],
    }

    role_id_map: dict[int, str] = {}
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_default() or role.managed:
            continue
        yaml_id = _slug(role.name)
        role_id_map[role.id] = yaml_id
        data["roles"].append({
            "id": yaml_id,
            "name": role.name,
            "color": f"#{role.color.value:06X}",
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "permissions": _perms_to_names(role.permissions),
        })

    def _ow_target(target: discord.Role | discord.Member) -> str:
        if isinstance(target, discord.Role):
            if target.is_default():
                return "@everyone"
            return role_id_map.get(target.id, _slug(target.name))
        return _slug(target.name)

    def _ow_list(channel: discord.abc.GuildChannel) -> list[dict]:
        out = []
        for tgt, ow in channel.overwrites.items():
            allow, deny = ow.pair()
            entry = {"target": _ow_target(tgt)}
            allow_names = _perms_to_names(allow)
            deny_names = _perms_to_names(deny)
            if allow_names:
                entry["allow"] = allow_names
            if deny_names:
                entry["deny"] = deny_names
            out.append(entry)
        return out

    for cat in sorted(guild.categories, key=lambda c: c.position):
        cat_entry = {
            "id": _slug(cat.name),
            "name": cat.name,
            "position": cat.position,
            "overwrites": _ow_list(cat),
            "channels": [],
        }
        for ch in cat.channels:
            ch_entry = {
                "id": _slug(f"{cat.name}_{ch.name}"),
                "name": ch.name,
                "type": (
                    "voice" if isinstance(ch, discord.VoiceChannel)
                    else "forum" if isinstance(ch, discord.ForumChannel)
                    else "announcement" if isinstance(ch, discord.TextChannel) and ch.is_news()
                    else "text"
                ),
            }
            topic = getattr(ch, "topic", None)
            if topic:
                ch_entry["topic"] = topic
            slow = getattr(ch, "slowmode_delay", 0)
            if slow:
                ch_entry["slowmode_delay"] = slow
            if isinstance(ch, discord.VoiceChannel):
                ch_entry["user_limit"] = ch.user_limit
            ow = _ow_list(ch)
            if ow:
                ch_entry["overwrites"] = ow
            cat_entry["channels"].append(ch_entry)
        data["categories"].append(cat_entry)

    buf = io.StringIO()
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.dump(data, buf)
    return buf.getvalue()
