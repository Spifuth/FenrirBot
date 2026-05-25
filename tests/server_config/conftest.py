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
