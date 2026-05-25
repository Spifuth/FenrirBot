"""Mapping between YAML UPPER_SNAKE_CASE permission names and discord.py attrs."""

from __future__ import annotations

import discord


class UnknownPermissionError(ValueError):
    """Raised when a YAML permission name is not in PERM_MAP."""


# UPPER_SNAKE_CASE -> discord.Permissions attribute name
PERM_MAP: dict[str, str] = {
    # General
    "ADMINISTRATOR": "administrator",
    "VIEW_AUDIT_LOG": "view_audit_log",
    "MANAGE_GUILD": "manage_guild",
    "MANAGE_ROLES": "manage_roles",
    "MANAGE_CHANNELS": "manage_channels",
    "MANAGE_WEBHOOKS": "manage_webhooks",
    "MANAGE_EMOJIS_AND_STICKERS": "manage_emojis",

    # Membership
    "KICK_MEMBERS": "kick_members",
    "BAN_MEMBERS": "ban_members",
    "MODERATE_MEMBERS": "moderate_members",
    "CREATE_INSTANT_INVITE": "create_instant_invite",
    "CHANGE_NICKNAME": "change_nickname",
    "MANAGE_NICKNAMES": "manage_nicknames",

    # Text channel
    "VIEW_CHANNEL": "view_channel",
    "SEND_MESSAGES": "send_messages",
    "SEND_TTS_MESSAGES": "send_tts_messages",
    "MANAGE_MESSAGES": "manage_messages",
    "EMBED_LINKS": "embed_links",
    "ATTACH_FILES": "attach_files",
    "READ_MESSAGE_HISTORY": "read_message_history",
    "MENTION_EVERYONE": "mention_everyone",
    "USE_EXTERNAL_EMOJIS": "use_external_emojis",
    "USE_EXTERNAL_STICKERS": "use_external_stickers",
    "ADD_REACTIONS": "add_reactions",
    "USE_APPLICATION_COMMANDS": "use_application_commands",

    # Threads
    "MANAGE_THREADS": "manage_threads",
    "CREATE_PUBLIC_THREADS": "create_public_threads",
    "CREATE_PRIVATE_THREADS": "create_private_threads",
    "SEND_MESSAGES_IN_THREADS": "send_messages_in_threads",

    # Voice
    "CONNECT": "connect",
    "SPEAK": "speak",
    "STREAM": "stream",
    "USE_VAD": "use_voice_activation",
    "PRIORITY_SPEAKER": "priority_speaker",
    "MUTE_MEMBERS": "mute_members",
    "DEAFEN_MEMBERS": "deafen_members",
    "MOVE_MEMBERS": "move_members",
    "REQUEST_TO_SPEAK": "request_to_speak",
}


def _resolve(name: str) -> str:
    attr = PERM_MAP.get(name)
    if attr is None:
        raise UnknownPermissionError(f"Permission inconnue : {name}")
    return attr


def to_permissions(perm_names: list[str]) -> discord.Permissions:
    """Build a `discord.Permissions` (none + the listed perms set to True)."""
    perms = discord.Permissions.none()
    for name in perm_names:
        setattr(perms, _resolve(name), True)
    return perms


def to_permission_overwrite(
    allow: list[str] | None = None,
    deny: list[str] | None = None,
) -> discord.PermissionOverwrite:
    """Build a channel-level overwrite (True=allow, False=deny, None=inherit)."""
    overwrite = discord.PermissionOverwrite()
    for name in allow or []:
        setattr(overwrite, _resolve(name), True)
    for name in deny or []:
        setattr(overwrite, _resolve(name), False)
    return overwrite
