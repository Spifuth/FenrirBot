"""Pydantic v2 models mirroring the server-spec YAML."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator, field_validator


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ChannelType(str, Enum):
    text = "text"
    voice = "voice"
    announcement = "announcement"
    forum = "forum"


class VerificationLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class ExplicitContentFilter(str, Enum):
    DISABLED = "DISABLED"
    MEMBERS_WITHOUT_ROLES = "MEMBERS_WITHOUT_ROLES"
    ALL_MEMBERS = "ALL_MEMBERS"


class DefaultNotifications(str, Enum):
    ALL_MESSAGES = "ALL_MESSAGES"
    ONLY_MENTIONS = "ONLY_MENTIONS"


class ReactionMode(str, Enum):
    toggle = "toggle"
    add_only = "add_only"


class MetaSpec(BaseModel):
    spec_version: str
    description: str | None = None
    target_audience: str | None = None
    language: str = "fr"


class ServerSettings(BaseModel):
    name: str
    verification_level: VerificationLevel = VerificationLevel.MEDIUM
    explicit_content_filter: ExplicitContentFilter = ExplicitContentFilter.ALL_MEMBERS
    default_notifications: DefaultNotifications = DefaultNotifications.ONLY_MENTIONS
    community_enabled: bool = False


class RoleSpec(BaseModel):
    id: str
    name: str
    color: str = "#000000"
    hoist: bool = False
    mentionable: bool = False
    permissions: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("color")
    @classmethod
    def _hex_color(cls, v: str) -> str:
        if not HEX_COLOR_RE.match(v):
            raise ValueError(f"color must be #RRGGBB hex, got: {v!r}")
        return v.upper()


class OverwriteSpec(BaseModel):
    target: str  # "@everyone" or a YAML role id
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)


class ChannelSpec(BaseModel):
    id: str
    name: str
    type: ChannelType = ChannelType.text
    topic: str | None = None
    slowmode_delay: int = 0
    user_limit: int = 0
    overwrites: list[OverwriteSpec] = Field(default_factory=list)
    first_message: str | None = None
    note: str | None = None


class CategorySpec(BaseModel):
    id: str
    name: str
    position: int = 0
    overwrites: list[OverwriteSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)


class WebhookSpec(BaseModel):
    id: str
    channel: str  # YAML channel id
    name: str
    avatar_url: str | None = None
    description: str | None = None


class ReactionBinding(BaseModel):
    emoji: str
    role: str  # YAML role id
    mode: ReactionMode = ReactionMode.toggle


class ReactionRolesSpec(BaseModel):
    channel: str  # YAML channel id
    message_marker: Literal["first_message"]
    bindings: list[ReactionBinding]


class Spec(BaseModel):
    meta: MetaSpec
    server: ServerSettings
    roles: list[RoleSpec]
    categories: list[CategorySpec]
    webhooks: list[WebhookSpec] = Field(default_factory=list)
    reaction_roles: list[ReactionRolesSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids_and_refs(self) -> "Spec":
        role_ids = [r.id for r in self.roles]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("duplicate role id in roles[]")

        chan_ids: list[str] = []
        for cat in self.categories:
            for ch in cat.channels:
                chan_ids.append(ch.id)
        if len(chan_ids) != len(set(chan_ids)):
            raise ValueError("duplicate channel id across categories[]")

        valid_targets = {"@everyone"} | set(role_ids)
        for cat in self.categories:
            for ow in cat.overwrites:
                if ow.target not in valid_targets:
                    raise ValueError(f"overwrite target {ow.target!r} not in roles or @everyone")
            for ch in cat.channels:
                for ow in ch.overwrites:
                    if ow.target not in valid_targets:
                        raise ValueError(f"overwrite target {ow.target!r} not in roles or @everyone")

        valid_chan_ids = set(chan_ids)
        for wh in self.webhooks:
            if wh.channel not in valid_chan_ids:
                raise ValueError(f"webhook {wh.id} references unknown channel {wh.channel}")
        for rr in self.reaction_roles:
            if rr.channel not in valid_chan_ids:
                raise ValueError(f"reaction_roles references unknown channel {rr.channel}")
            for b in rr.bindings:
                if b.role not in set(role_ids):
                    raise ValueError(f"reaction binding references unknown role {b.role}")
        return self
