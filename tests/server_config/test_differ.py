from dataclasses import dataclass, field
from typing import Any

import pytest

from src.server_config.differ import diff_roles, RoleDiff
from src.server_config.permissions import to_permissions


@dataclass
class FakeRole:
    name: str
    color_value: int = 0
    hoist: bool = False
    mentionable: bool = False
    permissions_value: int = 0

    @property
    def color(self):
        return type("C", (), {"value": self.color_value})()

    @property
    def permissions(self):
        return type("P", (), {"value": self.permissions_value})()


@dataclass
class FakeGuild:
    roles: list = field(default_factory=list)

    @property
    def default_role(self):
        return type("Everyone", (), {"name": "@everyone"})()


def _role_spec(**overrides):
    from src.server_config.models import RoleSpec
    base = {"id": "r1", "name": "Verified", "color": "#2ECC71", "hoist": True,
            "mentionable": False, "permissions": ["VIEW_CHANNEL", "SEND_MESSAGES"]}
    base.update(overrides)
    return RoleSpec(**base)


def test_diff_roles_create_when_missing():
    guild = FakeGuild(roles=[])
    diff = diff_roles(guild, [_role_spec()])
    assert len(diff.to_create) == 1
    assert diff.to_create[0].name == "Verified"
    assert diff.to_edit == []
    assert diff.unchanged == []


def test_diff_roles_unchanged_when_match():
    spec = _role_spec()
    existing = FakeRole(
        name="Verified",
        color_value=int("2ECC71", 16),
        hoist=True,
        mentionable=False,
        permissions_value=to_permissions(spec.permissions).value,
    )
    guild = FakeGuild(roles=[existing])
    diff = diff_roles(guild, [spec])
    assert diff.unchanged == [(spec, existing)]
    assert diff.to_create == []
    assert diff.to_edit == []


def test_diff_roles_edit_when_color_differs():
    spec = _role_spec()
    existing = FakeRole(
        name="Verified",
        color_value=0x000000,  # wrong color
        hoist=True,
        mentionable=False,
        permissions_value=to_permissions(spec.permissions).value,
    )
    guild = FakeGuild(roles=[existing])
    diff = diff_roles(guild, [spec])
    assert len(diff.to_edit) == 1
    edit = diff.to_edit[0]
    assert edit.role is existing
    assert "color" in edit.changed_fields


from src.server_config.differ import diff_channels
from src.server_config.models import CategorySpec, ChannelSpec


@dataclass
class FakeChannel:
    name: str
    topic: str = ""
    slowmode_delay: int = 0


@dataclass
class FakeCategoryChannel:
    name: str
    position: int = 0
    channels: list = field(default_factory=list)


@dataclass
class FakeGuildWithCats:
    categories: list = field(default_factory=list)


def test_diff_channels_reports_a_topic_change_as_an_edit():
    live = FakeCategoryChannel(name="General", channels=[FakeChannel(name="main", topic="old")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="General", channels=[
        ChannelSpec(id="ch1", name="main", topic="new")
    ])

    diff = diff_channels(guild, [cat])

    assert len(diff.to_edit) == 1
    assert diff.to_edit[0][1].name == "main"
    assert diff.unchanged == []


def test_diff_channels_reports_a_match_as_unchanged():
    live = FakeCategoryChannel(name="General", channels=[FakeChannel(name="main", topic="same")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="General", channels=[
        ChannelSpec(id="ch1", name="main", topic="same")
    ])

    diff = diff_channels(guild, [cat])

    assert diff.to_edit == []
    assert len(diff.unchanged) == 1


@dataclass
class FakeVoiceChannelLike:
    """A channel with no `topic`/`slowmode_delay` — like discord.VoiceChannel."""
    name: str
    user_limit: int = 0


def test_diff_channels_ignores_topic_on_a_channel_that_has_none():
    # apply_channels guards its topic edit with hasattr(existing, "topic"), so a
    # voice channel carrying an explicit spec topic is a no-op there. The diff
    # must not promise an edit the applier will silently skip.
    live = FakeCategoryChannel(name="Vocal", channels=[FakeVoiceChannelLike(name="general")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="Vocal", channels=[
        ChannelSpec(id="ch1", name="general", type="voice", topic="ignored by the applier")
    ])

    diff = diff_channels(guild, [cat])

    assert diff.to_edit == []
    assert len(diff.unchanged) == 1


def test_diff_channels_ignores_slowmode_on_a_channel_that_has_none():
    live = FakeCategoryChannel(name="Vocal", channels=[FakeVoiceChannelLike(name="general")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="Vocal", channels=[
        ChannelSpec(id="ch1", name="general", type="voice", slowmode_delay=30)
    ])

    diff = diff_channels(guild, [cat])

    assert diff.to_edit == []


def test_diff_channels_ignores_user_limit_on_a_non_voice_channel():
    # apply_channels gates user_limit on isinstance(existing, discord.VoiceChannel);
    # a text channel that happens to expose user_limit must not be reported.
    @dataclass
    class TextChannelWithUserLimit:
        name: str
        topic: str = ""
        slowmode_delay: int = 0
        user_limit: int = 99

    live = FakeCategoryChannel(name="General", channels=[TextChannelWithUserLimit(name="main")])
    guild = FakeGuildWithCats(categories=[live])
    cat = CategorySpec(id="c1", name="General", channels=[
        ChannelSpec(id="ch1", name="main", user_limit=0)
    ])

    diff = diff_channels(guild, [cat])

    assert diff.to_edit == []
