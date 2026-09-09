# Discord Server Config Cog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a declarative server-config subsystem to Fenrir: a `/server-config` slash command suite (`apply`, `validate`, `export`, `diff`, `webhooks reveal`) that reconciles a Discord guild against a versioned YAML spec.

**Architecture:** New top-level package `src/server_config/` with focused modules (models, loader, permissions mapper, resolver, state, differ, applier, exporter). A single cog `src/cogs/server_config.py` exposes the slash commands and the reaction-role listener. The YAML spec is the source of truth; the bot only reconciles. Idempotent matching by name (roles, categories), name+parent (channels), name+channel (webhooks), and author+first-line sentinel (first messages). Webhook URLs are secrets — never logged in full, never posted to a channel, always DM'd to the invoker.

**Tech Stack:** Python 3.11+, discord.py 2.x (already a dep), `pydantic` v2 (new), `ruamel.yaml` (new), `pytest` (new, dev only)

---

## Decisions locked in (from brainstorm)

- **YAML:** `ruamel.yaml` — preserves comments/order for `export`.
- **Validation:** `pydantic` v2 — schemas typed, fail-fast on parse.
- **Tests:** Pytest, isolated under `tests/server_config/` (project has no test suite today; this seed is OK).
- **Code location:** new top-level package `src/server_config/`.
- **Spec file location:** `specs/server-spec.yaml` at repo root.
- **Local state:** `data/server_config_state.json` (webhook id map, reaction-role bindings).
- **Intents:** `guilds`, `members`, `reactions`, `message_content` — user confirmed all enabled.

## Non-goals (out of scope, per brief)

- Cohorts per high school (`@Lycée-XYZ` scoping).
- Native Discord onboarding (`guild.edit_welcome_screen`, join questions).
- Pre-apply backups.

---

## File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/server_config/__init__.py` | Package marker, re-exports |
| Create | `src/server_config/models.py` | Pydantic v2 models for the spec |
| Create | `src/server_config/permissions.py` | `UPPER_SNAKE_CASE` → `discord.Permissions` / `PermissionOverwrite` |
| Create | `src/server_config/loader.py` | Read YAML file → validated `Spec` |
| Create | `src/server_config/state.py` | Read/write `data/server_config_state.json` |
| Create | `src/server_config/resolver.py` | YAML id → discord object cache |
| Create | `src/server_config/differ.py` | Compute structured diff between Spec and live guild |
| Create | `src/server_config/applier.py` | Apply diff to guild (supports `dry_run`) |
| Create | `src/server_config/exporter.py` | Live guild → YAML (ruamel) |
| Create | `src/server_config/reports.py` | Build embed summary + detailed `.txt` report |
| Create | `src/cogs/server_config.py` | Cog: slash commands + reaction-role listener |
| Create | `specs/server-spec.yaml` | Spec file (copied from brief) |
| Create | `tests/__init__.py` | Test package marker |
| Create | `tests/server_config/__init__.py` | Test sub-package marker |
| Create | `tests/server_config/conftest.py` | Shared fixtures (sample spec yaml string) |
| Create | `tests/server_config/test_permissions.py` | Unit tests: permission mapping |
| Create | `tests/server_config/test_loader.py` | Unit tests: YAML loading + Pydantic validation |
| Create | `tests/server_config/test_differ.py` | Unit tests: diff logic with fake guild objects |
| Create | `pytest.ini` | Pytest config: `testpaths`, `pythonpath` |
| Modify | `src/bot.py` | Add cog to `INITIAL_COGS`; ensure `intents.members` + `intents.reactions` |
| Modify | `requirements.txt` | Add `pydantic`, `ruamel.yaml`, `pytest` |
| Create | `src/server_config/README.md` | How to load the cog, spec format, gotchas |
| Create | `data/server_config_state.json` | Empty initial state (created on first write actually; just `{}` placeholder for git) |

---

## Milestone overview

1. **Tasks 1–3** — Bootstrap (deps, package skeleton, pytest config).
2. **Tasks 4–6** — Pure logic + tests: permissions, models+loader, state.
3. **Tasks 7–8** — Resolver + differ (with tests).
4. **Tasks 9–10** — `/server-config validate` + `/server-config diff` (read-only commands).
5. **Tasks 11–14** — Applier: roles → categories+channels → first_messages → reaction_roles.
6. **Task 15** — Applier: webhooks (with DM of URL).
7. **Task 16** — `/server-config apply` (dry_run-first, then real).
8. **Task 17** — Reaction-role listener.
9. **Task 18** — `/server-config webhooks reveal`.
10. **Task 19** — `/server-config export`.
11. **Task 20** — Wire cog, README, spec file, manual smoke test.

---

## Pre-flight (manual, do once)

These are human actions the engineer must do before / during the work:

1. **Discord Developer Portal** — Fenrir bot must have these Privileged Gateway Intents enabled (user confirmed already done): Presence, Server Members, Message Content.
2. **Invite scope** — bot must already be invited with `applications.commands` and these guild perms: `Manage Roles`, `Manage Channels`, `Manage Guild`, `View Audit Log`, `Manage Messages`, `Manage Webhooks`, `Add Reactions`, `Send Messages`, `Embed Links`, `Read Message History`, `View Channel`. (Re-invite if missing.)
3. **Bot role position** — the `Bot` (managed) role must already be at the top of the role hierarchy before running `apply`, otherwise role creation/edit will fail with `Forbidden` for high-ranked roles.

---

### Task 1: Add dependencies & bootstrap pytest

**Files:**
- Modify: `requirements.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/server_config/__init__.py`

- [ ] **Step 1: Add new dependencies to `requirements.txt`**

After the existing lines, append:

```
pydantic>=2.6.0
ruamel.yaml>=0.18.0
pytest>=8.0.0
```

- [ ] **Step 2: Install in venv**

Run:

```bash
cd /srv/project/python/FenrirBot
source venv/bin/activate
pip install -r requirements.txt
```

Expected: 3 new packages installed.

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_mode = auto
```

- [ ] **Step 4: Create empty test package markers**

```bash
mkdir -p tests/server_config
touch tests/__init__.py tests/server_config/__init__.py
```

- [ ] **Step 5: Smoke-run pytest (should collect 0 tests)**

Run: `pytest -q`
Expected: `no tests ran in ...` (exit 5, normal when test suite is empty).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini tests/__init__.py tests/server_config/__init__.py
git commit -m "chore: add pydantic/ruamel/pytest deps and bootstrap test layout for server_config"
```

---

### Task 2: Create the package skeleton

**Files:**
- Create: `src/server_config/__init__.py`

- [ ] **Step 1: Create package directory and marker**

```bash
mkdir -p src/server_config
```

Create `src/server_config/__init__.py` with:

```python
"""Declarative Discord server reconciliation.

YAML spec is the source of truth. This package parses, validates,
diffs, and applies a spec against a live discord.Guild.
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/__init__.py
git commit -m "feat(server_config): create package skeleton"
```

---

### Task 3: Copy the spec file into the repo

**Files:**
- Create: `specs/server-spec.yaml`

- [ ] **Step 1: Create the `specs/` directory and copy the source YAML**

```bash
mkdir -p specs
cp /home/nl/.claude/uploads/cc31b7bd-614b-4043-b9d6-afd155ba4b8f/b57d2140-discordserverspec.yaml specs/server-spec.yaml
```

- [ ] **Step 2: Verify contents start with the right header**

Run: `head -5 specs/server-spec.yaml`
Expected: line 1 begins with `# =====`, line 2 contains `Spec serveur Discord`.

- [ ] **Step 3: Commit**

```bash
git add specs/server-spec.yaml
git commit -m "feat(server_config): add reference server spec YAML"
```

---

### Task 4: Permissions mapper (TDD)

**Files:**
- Create: `src/server_config/permissions.py`
- Test: `tests/server_config/test_permissions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/server_config/test_permissions.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `pytest tests/server_config/test_permissions.py -v`
Expected: ImportError / ModuleNotFoundError on `src.server_config.permissions`.

- [ ] **Step 3: Implement `src/server_config/permissions.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/server_config/test_permissions.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/server_config/permissions.py tests/server_config/test_permissions.py
git commit -m "feat(server_config): permissions mapper + tests"
```

---

### Task 5: Pydantic models + YAML loader (TDD)

**Files:**
- Create: `src/server_config/models.py`
- Create: `src/server_config/loader.py`
- Create: `tests/server_config/conftest.py`
- Test: `tests/server_config/test_loader.py`

- [ ] **Step 1: Write a fixture for a minimal valid spec**

Create `tests/server_config/conftest.py`:

```python
import textwrap
import pytest


@pytest.fixture
def minimal_spec_yaml() -> str:
    return textwrap.dedent("""
    meta:
      spec_version: "1.0"
      description: "Minimal test spec"
    server:
      name: "Test Server"
      verification_level: HIGH
      explicit_content_filter: ALL_MEMBERS
      default_notifications: ONLY_MENTIONS
      community_enabled: false
    roles:
      - id: verified
        name: "🎓 Verified"
        color: "#2ECC71"
        hoist: true
        mentionable: false
        permissions: [VIEW_CHANNEL, SEND_MESSAGES]
    categories:
      - id: cat_general
        name: "General"
        position: 0
        overwrites:
          - target: "@everyone"
            deny: [VIEW_CHANNEL]
          - target: verified
            allow: [VIEW_CHANNEL, SEND_MESSAGES]
        channels:
          - id: ch_main
            name: "main"
            type: text
            topic: "Main chat"
    webhooks:
      - id: wh_feed
        channel: ch_main
        name: "Feed"
    reaction_roles:
      - channel: ch_main
        message_marker: "first_message"
        bindings:
          - emoji: "✅"
            role: verified
            mode: add_only
    """)


@pytest.fixture
def real_spec_path(tmp_path, minimal_spec_yaml):
    p = tmp_path / "spec.yaml"
    p.write_text(minimal_spec_yaml)
    return p
```

- [ ] **Step 2: Write failing tests**

Create `tests/server_config/test_loader.py`:

```python
import pytest
from pydantic import ValidationError

from src.server_config.loader import load_spec
from src.server_config.models import Spec, RoleSpec, ChannelType


def test_load_valid_spec(real_spec_path):
    spec = load_spec(real_spec_path)
    assert isinstance(spec, Spec)
    assert spec.meta.spec_version == "1.0"
    assert spec.server.name == "Test Server"
    assert len(spec.roles) == 1
    assert spec.roles[0].id == "verified"
    assert spec.roles[0].color == "#2ECC71"
    assert len(spec.categories) == 1
    assert spec.categories[0].channels[0].type == ChannelType.text


def test_load_rejects_invalid_color(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace('"#2ECC71"', '"not-a-color"')
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_rejects_unknown_channel_type(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace("type: text", "type: holographic")
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_rejects_duplicate_role_ids(tmp_path, minimal_spec_yaml):
    bad = minimal_spec_yaml.replace(
        "roles:\n      - id: verified",
        "roles:\n      - id: verified\n        name: x\n        permissions: []\n      - id: verified",
    )
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ValidationError):
        load_spec(p)


def test_load_real_spec_file():
    """The actual checked-in spec parses cleanly."""
    from pathlib import Path
    spec_path = Path(__file__).parent.parent.parent / "specs" / "server-spec.yaml"
    spec = load_spec(spec_path)
    assert spec.server.name  # not empty
    assert any(r.id == "lyceen_verifie" for r in spec.roles)
    assert any(c.id == "cat_accueil" for c in spec.categories)
```

- [ ] **Step 3: Run tests — expect ImportError**

Run: `pytest tests/server_config/test_loader.py -v`
Expected: ModuleNotFoundError on `src.server_config.models` / `loader`.

- [ ] **Step 4: Implement `src/server_config/models.py`**

```python
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
```

- [ ] **Step 5: Implement `src/server_config/loader.py`**

```python
"""Read a YAML spec file and return a validated `Spec`."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from .models import Spec


def load_spec(path: str | Path) -> Spec:
    """Parse YAML at `path` and return a validated `Spec`."""
    yaml = YAML(typ="safe")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    return Spec.model_validate(data)
```

- [ ] **Step 6: Run tests — expect green**

Run: `pytest tests/server_config/test_loader.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/server_config/models.py src/server_config/loader.py \
        tests/server_config/conftest.py tests/server_config/test_loader.py
git commit -m "feat(server_config): pydantic models + YAML loader with validation"
```

---

### Task 6: Local state file (webhook map + reaction-role bindings)

**Files:**
- Create: `src/server_config/state.py`
- Create: `data/server_config_state.json` (initial `{}`)

- [ ] **Step 1: Implement `src/server_config/state.py`**

```python
"""Persistent local state for server_config.

Tracks:
- webhook_yaml_id -> {discord_webhook_id, channel_id, name}
- discord_message_id -> {channel_id, bindings: {emoji: {role_id, mode}}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "server_config_state.json"


@dataclass
class WebhookEntry:
    discord_webhook_id: int
    channel_id: int
    name: str


@dataclass
class ReactionBindingEntry:
    role_id: int
    mode: str  # "toggle" | "add_only"


@dataclass
class ReactionMessageEntry:
    channel_id: int
    bindings: dict[str, ReactionBindingEntry] = field(default_factory=dict)


@dataclass
class State:
    webhooks: dict[str, WebhookEntry] = field(default_factory=dict)  # yaml_id -> entry
    reaction_messages: dict[int, ReactionMessageEntry] = field(default_factory=dict)  # msg_id -> entry

    def to_json(self) -> dict:
        return {
            "webhooks": {k: asdict(v) for k, v in self.webhooks.items()},
            "reaction_messages": {
                str(mid): {
                    "channel_id": rme.channel_id,
                    "bindings": {emoji: asdict(b) for emoji, b in rme.bindings.items()},
                }
                for mid, rme in self.reaction_messages.items()
            },
        }

    @classmethod
    def from_json(cls, data: dict) -> "State":
        s = cls()
        for yid, raw in (data.get("webhooks") or {}).items():
            s.webhooks[yid] = WebhookEntry(**raw)
        for mid_str, raw in (data.get("reaction_messages") or {}).items():
            bindings = {
                emoji: ReactionBindingEntry(**b)
                for emoji, b in (raw.get("bindings") or {}).items()
            }
            s.reaction_messages[int(mid_str)] = ReactionMessageEntry(
                channel_id=int(raw["channel_id"]),
                bindings=bindings,
            )
        return s


def load_state(path: Path = STATE_FILE) -> State:
    if not path.exists():
        return State()
    with open(path, "r", encoding="utf-8") as f:
        return State.from_json(json.load(f))


def save_state(state: State, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_json(), f, indent=2)
```

- [ ] **Step 2: Create initial empty state file**

```bash
echo '{}' > data/server_config_state.json
```

- [ ] **Step 3: Quick sanity test (one-shot)**

Run:

```bash
python -c "from src.server_config.state import load_state, save_state, State; s = load_state(); print(s); save_state(s); print('ok')"
```

Expected: prints `State(webhooks={}, reaction_messages={})` and `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/server_config/state.py data/server_config_state.json
git commit -m "feat(server_config): persistent local state for webhooks + reaction bindings"
```

---

### Task 7: Resolver — YAML id → live discord object

**Files:**
- Create: `src/server_config/resolver.py`

- [ ] **Step 1: Implement `src/server_config/resolver.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/resolver.py
git commit -m "feat(server_config): resolver — cache YAML id -> discord object"
```

---

### Task 8: Differ (TDD with fake guild objects)

**Files:**
- Create: `src/server_config/differ.py`
- Test: `tests/server_config/test_differ.py`

- [ ] **Step 1: Write failing tests**

Create `tests/server_config/test_differ.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `pytest tests/server_config/test_differ.py -v`
Expected: ModuleNotFoundError on `src.server_config.differ`.

- [ ] **Step 3: Implement `src/server_config/differ.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/server_config/test_differ.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full suite as a checkpoint**

Run: `pytest -v`
Expected: 13 passed total (5 perms + 5 loader + 3 differ).

- [ ] **Step 6: Commit**

```bash
git add src/server_config/differ.py tests/server_config/test_differ.py
git commit -m "feat(server_config): pure differ for roles + tests"
```

---

### Task 9: Stub cog with `/server-config validate`

**Files:**
- Create: `src/cogs/server_config.py`
- Modify: `src/bot.py`

- [ ] **Step 1: Create `src/cogs/server_config.py`**

```python
"""Slash commands for declarative server configuration."""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import ValidationError

from ..server_config.loader import load_spec


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SPEC = "specs/server-spec.yaml"


class ServerConfigCog(commands.Cog, name="ServerConfig"):
    """Reconcile the guild against a YAML spec."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="server-config", description="Reconciliation déclarative du serveur")

    @group.command(name="validate", description="Valider une spec YAML sans rien modifier")
    @app_commands.describe(path="Chemin de la spec (défaut: specs/server-spec.yaml)")
    @app_commands.default_permissions(administrator=True)
    async def validate_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)):
            await interaction.response.send_message("❌ Chemin hors du repo refusé.", ephemeral=True)
            return
        if not spec_path.exists():
            await interaction.response.send_message(f"❌ Fichier introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.response.send_message(
                f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ Spec valide — {len(spec.roles)} rôle(s), "
            f"{len(spec.categories)} catégorie(s), "
            f"{sum(len(c.channels) for c in spec.categories)} salon(s), "
            f"{len(spec.webhooks)} webhook(s), "
            f"{len(spec.reaction_roles)} bloc(s) reaction-roles.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))
```

- [ ] **Step 2: Register cog in `src/bot.py`**

Edit `src/bot.py` `INITIAL_COGS` list (between `"src.cogs.alerts"` and the closing bracket) so it becomes:

```python
    INITIAL_COGS = [
        "src.cogs.downtime",
        "src.cogs.status",
        "src.cogs.docker",
        "src.cogs.dashboard",
        "src.cogs.reports",
        "src.cogs.alerts",
        "src.cogs.server_config",
    ]
```

- [ ] **Step 3: Ensure required intents in `src/bot.py`**

In `FenrirBot.__init__`, replace:

```python
        intents = discord.Intents.default()
        intents.message_content = True
```

with:

```python
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.reactions = True
```

- [ ] **Step 4: Manual smoke test**

Rebuild & deploy locally if running in Docker (`./build.sh` then restart the management stack), OR run directly:

```bash
source venv/bin/activate
python run.py
```

Then in Discord, in the dev guild, run: `/server-config validate`
Expected: ephemeral message `✅ Spec valide — 7 rôle(s), 9 catégorie(s), ...`.

- [ ] **Step 5: Commit**

```bash
git add src/cogs/server_config.py src/bot.py
git commit -m "feat(server_config): cog with /server-config validate command + intents"
```

---

### Task 10: `/server-config diff` (computes diff, posts ephemeral summary)

**Files:**
- Modify: `src/cogs/server_config.py`
- Modify: `src/server_config/differ.py` (add channel/category diff stubs returning empty for now)
- Create: `src/server_config/reports.py`

- [ ] **Step 1: Extend `src/server_config/differ.py` with category + channel diffs**

Append:

```python
from .models import CategorySpec, ChannelSpec


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
```

- [ ] **Step 2: Create `src/server_config/reports.py`**

```python
"""Build human-readable summaries from diffs and apply results."""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

from .differ import RoleDiff, CategoryDiff, ChannelDiff


@dataclass
class Summary:
    roles_created: int = 0
    roles_edited: int = 0
    roles_unchanged: int = 0
    categories_created: int = 0
    categories_edited: int = 0
    categories_unchanged: int = 0
    channels_created: int = 0
    channels_edited: int = 0
    channels_unchanged: int = 0
    reactions_added: int = 0
    webhooks_created: int = 0
    webhooks_unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    detail_lines: list[str] = field(default_factory=list)


def summary_from_diffs(
    role_diff: RoleDiff, cat_diff: CategoryDiff, ch_diff: ChannelDiff
) -> Summary:
    s = Summary()
    s.roles_created = len(role_diff.to_create)
    s.roles_edited = len(role_diff.to_edit)
    s.roles_unchanged = len(role_diff.unchanged)
    s.categories_created = len(cat_diff.to_create)
    s.categories_edited = len(cat_diff.to_edit)
    s.categories_unchanged = len(cat_diff.unchanged)
    s.channels_created = len(ch_diff.to_create)
    s.channels_unchanged = len(ch_diff.unchanged)
    return s


def render_embed(s: Summary, dry_run: bool) -> discord.Embed:
    title = "🔍 Diff" if dry_run else "✅ Application terminée"
    color = 0xF1C40F if dry_run else 0x2ECC71
    if s.errors:
        color = 0xE74C3C
    e = discord.Embed(title=title, color=color)
    e.add_field(
        name="Roles",
        value=f"{s.roles_created} créés, {s.roles_edited} modifiés, {s.roles_unchanged} inchangés",
        inline=False,
    )
    e.add_field(
        name="Categories",
        value=f"{s.categories_created} créées, {s.categories_edited} modifiées, {s.categories_unchanged} inchangées",
        inline=False,
    )
    e.add_field(
        name="Channels",
        value=f"{s.channels_created} créés, {s.channels_edited} modifiés, {s.channels_unchanged} inchangés",
        inline=False,
    )
    e.add_field(
        name="Reactions",
        value=f"{s.reactions_added} posées",
        inline=False,
    )
    e.add_field(
        name="Webhooks",
        value=f"{s.webhooks_created} créés, {s.webhooks_unchanged} inchangés",
        inline=False,
    )
    e.add_field(name="Erreurs", value=str(len(s.errors)), inline=False)
    return e


def render_detail_file(s: Summary) -> discord.File:
    import io
    body = "\n".join(s.detail_lines) if s.detail_lines else "(no detail)"
    if s.errors:
        body += "\n\n--- ERRORS ---\n" + "\n".join(s.errors)
    return discord.File(io.BytesIO(body.encode("utf-8")), filename="server-config-report.txt")
```

- [ ] **Step 3: Add `/server-config diff` to the cog**

In `src/cogs/server_config.py`, add imports at the top:

```python
from ..server_config.differ import diff_roles, diff_categories, diff_channels
from ..server_config.reports import summary_from_diffs, render_embed, render_detail_file
```

Then add the command inside `ServerConfigCog`:

```python
    @group.command(name="diff", description="Diff lisible: spec vs serveur actuel")
    @app_commands.describe(path="Chemin de la spec (défaut: specs/server-spec.yaml)")
    @app_commands.default_permissions(administrator=True)
    async def diff_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        await interaction.response.defer(ephemeral=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)) or not spec_path.exists():
            await interaction.followup.send(f"❌ Chemin invalide ou introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.followup.send(f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return

        rd = diff_roles(guild, spec.roles)
        cd = diff_categories(guild, spec.categories)
        chd = diff_channels(guild, spec.categories)
        summary = summary_from_diffs(rd, cd, chd)
        for r in rd.to_create:
            summary.detail_lines.append(f"+ role: {r.name}")
        for e in rd.to_edit:
            summary.detail_lines.append(f"~ role: {e.spec.name} ({', '.join(e.changed_fields)})")
        for c in cd.to_create:
            summary.detail_lines.append(f"+ category: {c.name}")
        for cat, ch in chd.to_create:
            summary.detail_lines.append(f"+ channel: {cat.name} / {ch.name}")
        await interaction.followup.send(
            embed=render_embed(summary, dry_run=True),
            file=render_detail_file(summary),
            ephemeral=True,
        )
```

- [ ] **Step 4: Manual smoke test**

Run bot, then in the dev guild:

`/server-config diff`

Expected: ephemeral embed with counts + an attached `server-config-report.txt` listing each create/edit. On an empty server, every role/category/channel should appear as a `+` line.

- [ ] **Step 5: Commit**

```bash
git add src/server_config/differ.py src/server_config/reports.py src/cogs/server_config.py
git commit -m "feat(server_config): /server-config diff command + report helpers"
```

---

### Task 11: Applier — roles (with dry_run)

**Files:**
- Create: `src/server_config/applier.py`

- [ ] **Step 1: Implement `src/server_config/applier.py` (roles only first)**

```python
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
```

- [ ] **Step 2: Commit (no manual test yet — wired in via Task 16)**

```bash
git add src/server_config/applier.py
git commit -m "feat(server_config): applier — roles (create/edit/reposition) with dry_run"
```

---

### Task 12: Applier — categories + channels + overwrites

**Files:**
- Modify: `src/server_config/applier.py`

- [ ] **Step 1: Add to `src/server_config/applier.py`**

Append:

```python
from .models import CategorySpec, ChannelSpec, OverwriteSpec, ChannelType
from .permissions import to_permission_overwrite


def _build_overwrites(
    ctx: ApplyContext, overwrites: list[OverwriteSpec]
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    out: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}
    for ow in overwrites:
        target = ctx.resolver.resolve_target(ow.target)
        if target is None:
            ctx.err(f"overwrite target not found: {ow.target}")
            continue
        out[target] = to_permission_overwrite(allow=ow.allow, deny=ow.deny)
    return out


async def apply_categories(ctx: ApplyContext) -> None:
    for spec in ctx.spec.categories:
        existing = ctx.resolver.find_existing_category_by_name(spec.name)
        overwrites = _build_overwrites(ctx, spec.overwrites)
        if existing is None:
            ctx.log(f"+ category: {spec.name}")
            if ctx.dry_run:
                ctx.summary.categories_created += 1
                continue
            try:
                cat = await ctx.guild.create_category(
                    name=spec.name,
                    overwrites=overwrites,
                    position=spec.position,
                    reason="server_config apply",
                )
                ctx.resolver.register_category(spec.id, cat)
                ctx.summary.categories_created += 1
            except discord.Forbidden as e:
                ctx.err(f"category create forbidden: {spec.name} ({e})")
            except discord.HTTPException as e:
                ctx.err(f"category create HTTP: {spec.name} ({e})")
        else:
            ctx.resolver.register_category(spec.id, existing)
            needs_edit = existing.position != spec.position
            if needs_edit:
                ctx.log(f"~ category: {spec.name} (position)")
                if not ctx.dry_run:
                    try:
                        await existing.edit(position=spec.position, overwrites=overwrites,
                                            reason="server_config apply")
                        ctx.summary.categories_edited += 1
                    except discord.Forbidden as e:
                        ctx.err(f"category edit forbidden: {spec.name} ({e})")
                    except discord.HTTPException as e:
                        ctx.err(f"category edit HTTP: {spec.name} ({e})")
                else:
                    ctx.summary.categories_edited += 1
            else:
                # Still reconcile overwrites silently if they drifted
                if not ctx.dry_run:
                    try:
                        await existing.edit(overwrites=overwrites, reason="server_config apply")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                ctx.summary.categories_unchanged += 1


async def apply_channels(ctx: ApplyContext) -> None:
    for cat_spec in ctx.spec.categories:
        parent = ctx.resolver.categories_by_yaml_id.get(cat_spec.id)
        for ch_spec in cat_spec.channels:
            existing = ctx.resolver.find_existing_channel(ch_spec.name, parent)
            ch_overwrites = _build_overwrites(ctx, ch_spec.overwrites)

            if existing is None:
                ctx.log(f"+ channel: {cat_spec.name} / {ch_spec.name}")
                if ctx.dry_run:
                    ctx.summary.channels_created += 1
                    continue
                try:
                    new = await _create_channel(ctx, parent, ch_spec, ch_overwrites)
                    if new is not None:
                        ctx.resolver.register_channel(ch_spec.id, new)
                        ctx.summary.channels_created += 1
                except discord.Forbidden as e:
                    ctx.err(f"channel create forbidden: {ch_spec.name} ({e})")
                except discord.HTTPException as e:
                    ctx.err(f"channel create HTTP: {ch_spec.name} ({e})")
            else:
                ctx.resolver.register_channel(ch_spec.id, existing)
                # Reconcile topic/slowmode/user_limit/overwrites
                kwargs = {}
                if hasattr(existing, "topic") and ch_spec.topic is not None and existing.topic != ch_spec.topic:
                    kwargs["topic"] = ch_spec.topic
                if hasattr(existing, "slowmode_delay") and existing.slowmode_delay != ch_spec.slowmode_delay:
                    kwargs["slowmode_delay"] = ch_spec.slowmode_delay
                if isinstance(existing, discord.VoiceChannel) and existing.user_limit != ch_spec.user_limit:
                    kwargs["user_limit"] = ch_spec.user_limit
                if ch_overwrites:
                    kwargs["overwrites"] = ch_overwrites

                if kwargs:
                    ctx.log(f"~ channel: {cat_spec.name} / {ch_spec.name} ({list(kwargs)})")
                    if not ctx.dry_run:
                        try:
                            await existing.edit(reason="server_config apply", **kwargs)
                            ctx.summary.channels_edited += 1
                        except discord.Forbidden as e:
                            ctx.err(f"channel edit forbidden: {ch_spec.name} ({e})")
                        except discord.HTTPException as e:
                            ctx.err(f"channel edit HTTP: {ch_spec.name} ({e})")
                    else:
                        ctx.summary.channels_edited += 1
                else:
                    ctx.summary.channels_unchanged += 1


async def _create_channel(
    ctx: ApplyContext,
    parent: discord.CategoryChannel | None,
    ch_spec: ChannelSpec,
    overwrites: dict,
) -> discord.abc.GuildChannel | None:
    common = dict(name=ch_spec.name, category=parent, overwrites=overwrites, reason="server_config apply")
    if ch_spec.type == ChannelType.text:
        return await ctx.guild.create_text_channel(
            topic=ch_spec.topic or None,
            slowmode_delay=ch_spec.slowmode_delay,
            **common,
        )
    if ch_spec.type == ChannelType.announcement:
        return await ctx.guild.create_text_channel(
            topic=ch_spec.topic or None,
            news=True,
            **common,
        )
    if ch_spec.type == ChannelType.voice:
        return await ctx.guild.create_voice_channel(
            user_limit=ch_spec.user_limit,
            **common,
        )
    if ch_spec.type == ChannelType.forum:
        return await ctx.guild.create_forum(
            topic=ch_spec.topic or None,
            **common,
        )
    ctx.err(f"unknown channel type for {ch_spec.name}: {ch_spec.type}")
    return None
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/applier.py
git commit -m "feat(server_config): applier — categories + channels + overwrites"
```

---

### Task 13: Applier — first_message (idempotent via author + first line)

**Files:**
- Modify: `src/server_config/applier.py`

- [ ] **Step 1: Append to `src/server_config/applier.py`**

```python
async def _find_existing_first_message(
    bot_user: discord.ClientUser, channel: discord.TextChannel, first_line: str
) -> discord.Message | None:
    """Find a bot-authored message whose first line matches `first_line`."""
    async for msg in channel.history(limit=50, oldest_first=True):
        if msg.author.id != bot_user.id:
            continue
        msg_first = msg.content.splitlines()[0] if msg.content else ""
        if msg_first.strip() == first_line.strip():
            return msg
    return None


async def apply_first_messages(ctx: ApplyContext) -> dict[str, discord.Message]:
    """Returns yaml_channel_id -> first_message Message (created or found)."""
    out: dict[str, discord.Message] = {}
    bot_user = ctx.bot.user
    assert bot_user is not None
    for cat_spec in ctx.spec.categories:
        for ch_spec in cat_spec.channels:
            if not ch_spec.first_message:
                continue
            channel = ctx.resolver.channels_by_yaml_id.get(ch_spec.id)
            if not isinstance(channel, discord.TextChannel):
                continue
            first_line = ch_spec.first_message.splitlines()[0]

            if ctx.dry_run:
                ctx.log(f"+ first_message (dry): {ch_spec.name}")
                continue

            try:
                existing = await _find_existing_first_message(bot_user, channel, first_line)
            except discord.Forbidden:
                ctx.err(f"history read forbidden in {ch_spec.name}")
                continue

            if existing is not None:
                out[ch_spec.id] = existing
                continue

            ctx.log(f"+ first_message: {ch_spec.name}")
            try:
                msg = await channel.send(ch_spec.first_message)
                out[ch_spec.id] = msg
            except discord.Forbidden as e:
                ctx.err(f"first_message send forbidden in {ch_spec.name}: {e}")
            except discord.HTTPException as e:
                ctx.err(f"first_message send HTTP in {ch_spec.name}: {e}")
    return out
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/applier.py
git commit -m "feat(server_config): applier — idempotent first_message via author+line sentinel"
```

---

### Task 14: Applier — reaction roles (post reactions + persist binding)

**Files:**
- Modify: `src/server_config/applier.py`

- [ ] **Step 1: Append to `src/server_config/applier.py`**

```python
from .state import State, ReactionMessageEntry, ReactionBindingEntry


async def apply_reaction_roles(
    ctx: ApplyContext,
    first_messages: dict[str, discord.Message],
    state: State,
) -> None:
    for block in ctx.spec.reaction_roles:
        # We only support message_marker == "first_message" for now.
        msg = first_messages.get(block.channel)
        if msg is None and not ctx.dry_run:
            ctx.err(f"reaction_roles: no first_message for channel {block.channel}")
            continue

        for binding in block.bindings:
            role = ctx.resolver.roles_by_yaml_id.get(binding.role)
            if role is None and not ctx.dry_run:
                ctx.err(f"reaction binding: role {binding.role} unresolved")
                continue
            ctx.log(f"+ reaction: {binding.emoji} -> {binding.role} ({binding.mode.value})")
            if ctx.dry_run:
                ctx.summary.reactions_added += 1
                continue
            assert msg is not None and role is not None
            # Add the reaction if not already present
            try:
                await msg.add_reaction(binding.emoji)
            except discord.HTTPException as e:
                ctx.err(f"add_reaction failed for {binding.emoji}: {e}")
                continue

            entry = state.reaction_messages.setdefault(
                msg.id, ReactionMessageEntry(channel_id=msg.channel.id, bindings={})
            )
            entry.bindings[binding.emoji] = ReactionBindingEntry(
                role_id=role.id, mode=binding.mode.value
            )
            ctx.summary.reactions_added += 1
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/applier.py
git commit -m "feat(server_config): applier — reaction roles posting + state persistence"
```

---

### Task 15: Applier — webhooks (with DM of URL)

**Files:**
- Modify: `src/server_config/applier.py`

- [ ] **Step 1: Append to `src/server_config/applier.py`**

```python
from .state import WebhookEntry


def _mask_webhook_url(url: str) -> str:
    """https://discord.com/api/webhooks/{id}/{token} -> .../{id}/****"""
    if "/webhooks/" not in url:
        return "****"
    head, _, token_part = url.rpartition("/")
    return f"{head}/****"


async def apply_webhooks(
    ctx: ApplyContext,
    state: State,
    invoker: discord.User | discord.Member,
) -> list[tuple[str, str]]:
    """Returns list of (yaml_id, url) for *newly created* webhooks only."""
    created: list[tuple[str, str]] = []
    for wh_spec in ctx.spec.webhooks:
        channel = ctx.resolver.channels_by_yaml_id.get(wh_spec.channel)
        if not isinstance(channel, discord.TextChannel):
            ctx.err(f"webhook {wh_spec.id}: target channel {wh_spec.channel} not a text channel")
            continue

        if ctx.dry_run:
            ctx.log(f"+ webhook (dry): {wh_spec.name} in #{channel.name}")
            ctx.summary.webhooks_created += 1
            continue

        try:
            existing = await channel.webhooks()
        except discord.Forbidden as e:
            ctx.err(f"webhook list forbidden in {channel.name}: {e}")
            continue

        match = next((w for w in existing if w.name == wh_spec.name), None)
        if match is not None:
            state.webhooks[wh_spec.id] = WebhookEntry(
                discord_webhook_id=match.id, channel_id=channel.id, name=match.name
            )
            ctx.summary.webhooks_unchanged += 1
            ctx.log(f"= webhook: {wh_spec.name} (existing, id={match.id})")
            continue

        try:
            new = await channel.create_webhook(
                name=wh_spec.name, reason="server_config apply"
            )
        except discord.Forbidden as e:
            ctx.err(f"webhook create forbidden in {channel.name}: {e}")
            continue
        except discord.HTTPException as e:
            ctx.err(f"webhook create HTTP in {channel.name}: {e}")
            continue

        state.webhooks[wh_spec.id] = WebhookEntry(
            discord_webhook_id=new.id, channel_id=channel.id, name=new.name
        )
        ctx.summary.webhooks_created += 1
        # Logging: masked only
        ctx.log(f"+ webhook: {wh_spec.name} (id={new.id}, url=<DM only>)")
        created.append((wh_spec.id, new.url))

    # DM the invoker once, with all new webhook URLs
    if created:
        try:
            dm = await invoker.create_dm()
            lines = ["**Nouveaux webhooks créés (URLs = SECRETS)**", ""]
            for yid, url in created:
                lines.append(f"• `{yid}` — {url}")
            lines += [
                "",
                "Stocke ces URLs dans Infisical (path: `homelab/discord-bot/webhooks/...`).",
                "Tu peux les re-récupérer plus tard via `/server-config webhooks reveal id:<yaml_id>`.",
            ]
            await dm.send("\n".join(lines))
        except discord.Forbidden:
            ctx.err("DM failed (DMs closed?) — URLs disponibles via /server-config webhooks reveal")
    return created
```

- [ ] **Step 2: Commit**

```bash
git add src/server_config/applier.py
git commit -m "feat(server_config): applier — webhooks with masked logs + DM of URL"
```

---

### Task 16: `/server-config apply` command (orchestrates the applier)

**Files:**
- Modify: `src/cogs/server_config.py`

- [ ] **Step 1: Add imports + command to the cog**

Add imports near the top of `src/cogs/server_config.py`:

```python
from ..server_config.applier import (
    ApplyContext, apply_roles, apply_categories, apply_channels,
    apply_first_messages, apply_reaction_roles, apply_webhooks,
)
from ..server_config.resolver import Resolver
from ..server_config.state import load_state, save_state
from ..server_config.reports import Summary
```

Inside `ServerConfigCog`, append:

```python
    @group.command(name="apply", description="Appliquer la spec au serveur")
    @app_commands.describe(
        path="Chemin de la spec (défaut: specs/server-spec.yaml)",
        dry_run="Si True, log uniquement sans rien modifier (défaut: True)",
    )
    @app_commands.default_permissions(administrator=True)
    async def apply_cmd(
        self,
        interaction: discord.Interaction,
        path: str = DEFAULT_SPEC,
        dry_run: bool = True,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)) or not spec_path.exists():
            await interaction.followup.send(f"❌ Chemin invalide ou introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.followup.send(f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return

        # Bot hierarchy warning: if bot isn't above the highest non-default role,
        # role create/edit of roles ranked above it will fail with Forbidden.
        # We don't abort — applier handles Forbidden per-role and reports as errors.
        me = guild.me
        if me is not None:
            highest_other = max((r.position for r in guild.roles if not r.is_default()), default=0)
            if me.top_role.position <= highest_other:
                await interaction.followup.send(
                    "⚠️ Le rôle du bot n'est pas au sommet de la hiérarchie. "
                    "Certaines opérations sur les rôles haut-classés peuvent échouer. "
                    "Best-effort en cours…",
                    ephemeral=True,
                )

        state = load_state()
        resolver = Resolver(guild=guild, spec=spec)
        summary = Summary()
        ctx = ApplyContext(
            bot=self.bot, guild=guild, spec=spec,
            resolver=resolver, summary=summary, dry_run=dry_run,
        )

        await apply_roles(ctx)
        await apply_categories(ctx)
        await apply_channels(ctx)
        first_msgs = await apply_first_messages(ctx)
        await apply_reaction_roles(ctx, first_messages=first_msgs, state=state)
        await apply_webhooks(ctx, state=state, invoker=interaction.user)

        if not dry_run:
            save_state(state)

        await interaction.followup.send(
            embed=render_embed(summary, dry_run=dry_run),
            file=render_detail_file(summary),
            ephemeral=True,
        )
```

- [ ] **Step 2: Manual smoke test — dry_run first, on a throwaway guild**

Restart Fenrir. In a **throwaway test guild** (NOT prod):

1. `/server-config apply path:specs/server-spec.yaml dry_run:true`
   → ephemeral embed reports counts; report .txt shows `[DRY] +` lines for everything.
2. `/server-config apply path:specs/server-spec.yaml dry_run:false`
   → real creation. Check Discord UI: roles, categories, channels, first_messages, reactions, webhooks created. Invoker receives a DM with the webhook URLs.
3. Run `/server-config apply dry_run:false` again on the now-populated guild
   → counts must show `0 créés, 0 modifiés, N inchangés` everywhere. No DM (no new webhooks).

- [ ] **Step 3: Commit**

```bash
git add src/cogs/server_config.py
git commit -m "feat(server_config): /server-config apply orchestrator + dry_run-first"
```

---

### Task 17: Reaction-role listener (`on_raw_reaction_add` / `_remove`)

**Files:**
- Modify: `src/cogs/server_config.py`

- [ ] **Step 1: Add listeners inside `ServerConfigCog`**

```python
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, added: bool):
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        state = load_state()
        msg_entry = state.reaction_messages.get(payload.message_id)
        if not msg_entry:
            return
        emoji_key = str(payload.emoji)
        binding = msg_entry.bindings.get(emoji_key)
        if not binding:
            return

        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        role = guild.get_role(binding.role_id)
        if member is None or role is None:
            return

        try:
            if added:
                if role not in member.roles:
                    await member.add_roles(role, reason="server_config reaction-role")
            else:
                if binding.mode == "toggle" and role in member.roles:
                    await member.remove_roles(role, reason="server_config reaction-role toggle off")
                # add_only: do nothing on removal
        except discord.Forbidden:
            return
```

- [ ] **Step 2: Manual smoke test**

In the test guild (after a real `apply` ran):

- React with ✅ on the rules first_message as a non-admin alt account → user gets `🎓 Lycéen vérifié`.
- React with 💻 on the interests first_message → user gets `💻 Curieux dev`.
- Un-react with 💻 → role is removed (toggle mode).
- Un-react with ✅ → role is **kept** (add_only mode).

- [ ] **Step 3: Commit**

```bash
git add src/cogs/server_config.py
git commit -m "feat(server_config): reaction-role listener (add_only + toggle modes)"
```

---

### Task 18: `/server-config webhooks reveal`

**Files:**
- Modify: `src/cogs/server_config.py`

- [ ] **Step 1: Add a sub-group `webhooks` with `reveal` subcommand**

In `src/cogs/server_config.py`, after the `group = app_commands.Group(...)` line, add:

```python
    webhooks_group = app_commands.Group(
        parent=group, name="webhooks", description="Outils webhooks"
    )
```

Then add the command:

```python
    @webhooks_group.command(name="reveal", description="Re-DM l'URL d'un webhook existant (par id YAML)")
    @app_commands.describe(id="Identifiant YAML du webhook (ex: wh_questions_live)")
    @app_commands.default_permissions(administrator=True)
    async def webhooks_reveal(self, interaction: discord.Interaction, id: str):
        await interaction.response.defer(ephemeral=True)
        state = load_state()
        entry = state.webhooks.get(id)
        if entry is None:
            await interaction.followup.send(f"❌ Aucun webhook connu pour id `{id}`.", ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return
        channel = guild.get_channel(entry.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(f"❌ Salon introuvable (id={entry.channel_id}).", ephemeral=True)
            return
        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            await interaction.followup.send("❌ Manque la permission `Manage Webhooks`.", ephemeral=True)
            return
        wh = next((w for w in webhooks if w.id == entry.discord_webhook_id), None)
        if wh is None:
            await interaction.followup.send("❌ Webhook supprimé côté Discord. Re-run /apply.", ephemeral=True)
            return
        try:
            dm = await interaction.user.create_dm()
            await dm.send(f"🔐 Webhook `{id}`\n{wh.url}")
            await interaction.followup.send("📬 URL envoyée en DM.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ DM impossible (DMs fermés). Ouvre tes DMs et réessaie.", ephemeral=True
            )
```

- [ ] **Step 2: Manual smoke test**

Run: `/server-config webhooks reveal id:wh_questions_live`
Expected: ephemeral `📬 URL envoyée en DM.` + a DM with the full URL. POSTing JSON `{"content": "test"}` to that URL should land a message in `#❓-questions-live`.

- [ ] **Step 3: Commit**

```bash
git add src/cogs/server_config.py
git commit -m "feat(server_config): /server-config webhooks reveal subcommand"
```

---

### Task 19: `/server-config export`

**Files:**
- Create: `src/server_config/exporter.py`
- Modify: `src/cogs/server_config.py`

- [ ] **Step 1: Implement `src/server_config/exporter.py`**

```python
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
```

- [ ] **Step 2: Add `/server-config export` to the cog**

Add to `src/cogs/server_config.py`:

```python
from ..server_config.exporter import export_guild
```

Append inside `ServerConfigCog`:

```python
    @group.command(name="export", description="Exporter l'état actuel du serveur en YAML")
    @app_commands.describe(output="Nom du fichier à attacher (défaut: server-spec-export.yaml)")
    @app_commands.default_permissions(administrator=True)
    async def export_cmd(
        self,
        interaction: discord.Interaction,
        output: str = "server-spec-export.yaml",
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return
        yaml_str = export_guild(guild)
        import io
        f = discord.File(io.BytesIO(yaml_str.encode("utf-8")), filename=output)
        await interaction.followup.send("📤 Export prêt.", file=f, ephemeral=True)
```

- [ ] **Step 3: Manual smoke test**

Run: `/server-config export`
Expected: ephemeral message with an attached YAML file. Open it; should parse cleanly via `/server-config validate path:<file>` once placed in `specs/`.

- [ ] **Step 4: Commit**

```bash
git add src/server_config/exporter.py src/cogs/server_config.py
git commit -m "feat(server_config): /server-config export — live guild to YAML"
```

---

### Task 20: README + final regression sweep

**Files:**
- Create: `src/server_config/README.md`

- [ ] **Step 1: Write `src/server_config/README.md`**

```markdown
# server_config

Reconcile a Discord guild against a YAML spec.

## Slash commands

| Command | Effect |
|---------|--------|
| `/server-config validate path:<path>` | Parse + validate, no Discord writes. |
| `/server-config diff path:<path>` | Diff spec vs live guild, ephemeral report. |
| `/server-config apply path:<path> dry_run:<bool=true>` | Reconcile. `dry_run=true` logs only. |
| `/server-config export output:<path>` | Dump current guild state as YAML. |
| `/server-config webhooks reveal id:<yaml_id>` | Re-DM the URL of a known webhook. |

All commands require **Administrator**.

## Spec file

Default location: `specs/server-spec.yaml` (repo root). Format documented inline in the file.

## Idempotence contract

Matching keys (must stay stable in the spec):

- Roles: by **name**.
- Categories: by **name**.
- Channels: by **name + parent category**.
- Webhooks: by **name + channel**.
- `first_message`: by **bot author + first line**.

Re-running `apply` should always show `0 créés, 0 modifiés`.

## Gotchas

- **Manual rename on Discord** → bot will re-create. YAML is the source of truth.
- **Bot role position** — must be above all managed roles before apply.
- **Privileged intents** — `Server Members Intent` and `Message Content Intent` must be enabled in the Developer Portal.
- **Webhook URLs are secrets** — never logged in full, never posted to a channel. DM'd to the invoker. Re-fetch via `/server-config webhooks reveal`.
- **`COMMUNITY` features** — `announcement` and `forum` channels require the guild to have Community enabled. Not toggled by this bot.

## Local state

`data/server_config_state.json` persists:
- YAML webhook id → Discord webhook id (so `reveal` can find it).
- Reaction-role message id → emoji → role id + mode.

## Tests

```bash
source venv/bin/activate
pytest -q
```
```

- [ ] **Step 2: Full test suite + manual idempotence check**

Run: `pytest -q`
Expected: all tests green.

In the test guild, run a 3rd `apply dry_run:false`:
Expected: every count `0 créés, 0 modifiés`. No DM.

- [ ] **Step 3: Commit**

```bash
git add src/server_config/README.md
git commit -m "docs(server_config): README — commands, idempotence contract, gotchas"
```

- [ ] **Step 4: Build & deploy**

```bash
./build.sh
```

Then redeploy via the nebula stack as per project convention.

---

## Acceptance checklist (from brief)

Run these on the test guild after a clean `apply dry_run:false`:

- [ ] `/server-config validate path:specs/server-spec.yaml` → OK.
- [ ] `dry_run:true` on empty guild → logs creations, creates nothing.
- [ ] `dry_run:false` on empty guild → creates everything in spec.
- [ ] Re-run → `0` changes (idempotence).
- [ ] React ✅ on rules → `🎓 Lycéen vérifié` granted. Un-react → role kept (add_only).
- [ ] React 💻/🤖/🔐/🛠️ on interests → role toggled.
- [ ] First apply: `wh_questions_live` created in `#❓-questions-live`, URL DM'd.
- [ ] `POST {"content":"test"}` to that URL posts in the channel.
- [ ] `/server-config webhooks reveal id:wh_questions_live` re-DMs the URL.
- [ ] Re-apply does NOT recreate the webhook, does NOT DM again.
- [ ] Only members with `ADMINISTRATOR` can invoke any subcommand.
- [ ] Detail log: 1 line per significant action, no full webhook URL leaked.
