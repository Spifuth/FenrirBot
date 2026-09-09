import pytest
import discord

from src.server_config.permissions import (
    PERM_MAP,
    to_permissions,
    to_permission_overwrite,
    UnknownPermissionError,
)


def test_permission_map_includes_all_used_in_spec():
    required = {
        "VIEW_CHANNEL", "READ_MESSAGE_HISTORY", "SEND_MESSAGES", "EMBED_LINKS",
        "ATTACH_FILES", "ADD_REACTIONS", "USE_EXTERNAL_EMOJIS", "CONNECT", "SPEAK",
        "STREAM", "USE_APPLICATION_COMMANDS", "MENTION_EVERYONE", "MANAGE_MESSAGES",
        "MANAGE_THREADS", "KICK_MEMBERS", "MODERATE_MEMBERS", "MUTE_MEMBERS",
        "DEAFEN_MEMBERS", "MOVE_MEMBERS", "VIEW_AUDIT_LOG", "ADMINISTRATOR",
        "CREATE_PUBLIC_THREADS", "USE_VAD", "MANAGE_WEBHOOKS",
    }
    missing = required - set(PERM_MAP.keys())
    assert not missing, f"PERM_MAP missing: {missing}"


def test_to_permissions_sets_attributes():
    perms = to_permissions(["VIEW_CHANNEL", "SEND_MESSAGES"])
    assert perms.view_channel is True
    assert perms.send_messages is True
    assert perms.administrator is False


def test_to_permissions_use_vad_maps_to_use_voice_activation():
    perms = to_permissions(["USE_VAD"])
    assert perms.use_voice_activation is True


def test_to_permissions_unknown_raises():
    with pytest.raises(UnknownPermissionError):
        to_permissions(["NOT_A_REAL_PERM"])


def test_to_permission_overwrite_allow_and_deny():
    ow = to_permission_overwrite(allow=["SEND_MESSAGES"], deny=["ADD_REACTIONS"])
    assert ow.send_messages is True
    assert ow.add_reactions is False
    # untouched perms should be None (i.e. inherited)
    assert ow.view_channel is None
