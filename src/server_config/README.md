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
