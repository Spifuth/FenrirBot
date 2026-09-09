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
