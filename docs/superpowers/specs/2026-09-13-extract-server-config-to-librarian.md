# Spec: Extract `server_config` into a dedicated bot — **The Librarian**

**Date:** 2026-09-13
**Status:** Approved
**Spans two repos:** `Spifuth/FenrirBot` (removal) and `Spifuth/the-librarian` (new)

## Context

FenrirBot is a homelab-ops bot: Docker control via socket-proxy, downtime/maintenance
announcements, VictoriaMetrics reports, Grafana alerts. The `server_config` cog is a
different domain entirely — declarative reconciliation of a *Discord guild* against a
YAML spec (roles, categories, channels, first messages, reaction roles, webhooks). It
shares no state, no client and no external dependency with the rest of the bot.

The extraction is unusually cheap because the code is already isolated: the entire
`src/server_config/` package imports **nothing** from FenrirBot, and the cog imports
exactly one FenrirBot symbol — `src.utils.permissions.admin_only`.

**Driver:** separation of concerns only. Behaviour is unchanged: single guild, one
spec baked into the image. This is a lift-and-shift, not a redesign.

## Goal

A new standalone bot, **The Librarian**, owning the `/server-config` command group and
its reaction-role listeners. FenrirBot drops from seven cogs to six and loses the
Manage Roles/Channels/Webhooks surface.

## Identity and placement

| Thing | Value |
|---|---|
| Repo | `github.com/Spifuth/the-librarian` (private, matching FenrirBot) |
| Source path | `/srv/project/python/the-librarian/` |
| Image | `librarian:latest`, built locally via `./build.sh` (FenrirBot pattern) |
| Container | `librarian` |
| Compose | `/srv/nebula/docker/services/apps/librarian/librarian.yml` |
| Nebula project | `apps` — alongside `lycee-bot` and `cutebot` |
| Infisical | project `apps`, env `prod`, prefix `LIBRARIAN_` |
| Appdata | `${DOCKERDIR}/appdata/librarian/data` → `/app/data` |

## What moves, verbatim

Copied byte-for-byte unless noted. No refactoring during the lift — the point is that
the existing tests keep passing.

| From `FenrirBot/` | To `the-librarian/` | Change |
|---|---|---|
| `src/server_config/` (10 files, ~1100 lines) | `src/server_config/` | none |
| `src/cogs/server_config.py` (282 lines) | `src/cogs/server_config.py` | **none** — see below |
| `tests/server_config/` (4 test files + conftest) | `tests/server_config/` | none |
| `specs/server-spec.yaml` (757 lines) | `specs/server-spec.yaml` | none |
| `src/utils/permissions.py` | `src/utils/permissions.py` | **copied, not moved** |
| `pytest.ini` | `pytest.ini` | none |

Plus the empty `__init__.py` files for `src/`, `src/cogs/`, `src/utils/`,
`tests/`, `tests/server_config/`.

The cog needs **zero edits**. Its two FenrirBot-relative imports
(`..utils.permissions`, `..server_config.*`) resolve identically because the new repo
keeps the same `src/cogs/` + `src/utils/` + `src/server_config/` layout, and
`REPO_ROOT = Path(__file__).resolve().parent.parent.parent` re-anchors itself to the new
repo root for free.

> `admin_only` is used by seven FenrirBot cogs (`dashboard`, `docker`, `status`,
> `alerts`, `reports`, `downtime`, `server_config`). It must stay in FenrirBot. The
> Librarian gets its own copy — 17 lines, no shared-library dependency between the two
> repos.

## What is written fresh

Modelled on FenrirBot's build pattern and lycee-bot's minimal runtime:

- **`run.py`** — entry point; exits non-zero with a clear message if `DISCORD_TOKEN` is absent.
- **`src/bot.py`** — `commands.Bot` subclass; explicit `INITIAL_COGS = ["src.cogs.server_config"]`
  (FenrirBot's explicit-list style, not lycee-bot's `pkgutil` auto-discovery — one cog
  does not need discovery), `setup_hook` loads it and syncs the tree.
- **`src/config.py`** — dataclass `Config` from env: `token` (required), `command_prefix`
  (default `!`). Nothing else; the Librarian consumes no URLs or API keys.
- **`Dockerfile`** — `python:3.12-alpine`, `COPY src/ specs/ run.py`, unprivileged user
  `uid 10001`, `mkdir -p /app/data`, `chown -R`. Mirrors FenrirBot's, minus the
  socket-proxy note.
- **`build.sh`** — `docker build --pull -t librarian:latest .` plus the deploy hint
  (`./scripts/start-docker.sh up apps`). Byte-for-byte FenrirBot's shape.
- **`requirements.txt`** — `discord.py`, `python-dotenv`, `pydantic`, `ruamel.yaml`.
  **Drops `docker` and the direct `aiohttp` pin** — neither is used by `server_config`
  (`aiohttp` still arrives transitively via discord.py).
- **`README.md`**, **`CLAUDE.md`**, **`.gitignore`**, **`cspell.json`** — repo hygiene,
  FenrirBot's shape.
- **`librarian.yml`** — compose service, see below.

### Intents

```python
intents = discord.Intents.default()   # guilds
intents.members = True                # guild.get_member / fetch_member on reaction
intents.reactions = True              # on_raw_reaction_add / _remove
```

`message_content` is **not** enabled — `server_config` never reads message text. This is
a privileged intent FenrirBot needs and the Librarian does not.

`members` *is* privileged and must be toggled on in the Discord developer portal, or the
reaction-role listeners fail at `fetch_member`.

### Compose service

Networks: **`default` only.** No `socket_proxy` (no Docker access), no `t3_proxy` (no
ingress — the Librarian has no HTTP surface at all). Otherwise the FenrirBot service
shape: `no-new-privileges`, `restart: unless-stopped`, `diun.enable=false`, cpu/mem
limits from Infisical, `TZ`.

Environment: `DISCORD_TOKEN: ${LIBRARIAN_DISCORD_TOKEN}` and `TZ`. That is the whole
surface.

Per the estate rule, `/srv/nebula/projects/apps/` must already contain the `.env`
symlink to `../../.env` — it does (lycee-bot and cutebot run there).

## The spec file stays baked into the image

`COPY specs/ ./specs/`, as today. Changing a channel means edit → commit → `./build.sh`
→ recreate. Slower than a bind mount, and that is the point: the spec is the source of
truth for the server and stays git-versioned and reviewable.

The path-traversal guard is preserved unchanged: `path` is resolved and rejected unless
`is_relative_to(REPO_ROOT)`. `REPO_ROOT` is computed from `__file__`, so it resolves to
the new repo root (`/app` in the container) with no code change.

## State migration — the dangerous part

`${DOCKERDIR}/appdata/fenrirbot/data/server_config_state.json` currently holds **1 live
webhook mapping and 4 reaction-role message bindings**.

If this file does not move, the failure is **silent**: the Librarian boots healthy,
`/server-config apply` works, and reaction roles simply stop granting roles because no
message id is tracked. The webhook URL behind `wh_*` becomes unrecoverable via
`/server-config webhooks reveal` — Discord will not re-show a webhook token.

Migration, before the Librarian's first boot:

1. `mkdir -p ${DOCKERDIR}/appdata/librarian/data`
2. Copy (do not move) `server_config_state.json` into it — FenrirBot keeps its copy
   until cutover is proven, as the rollback path.
3. `chown 10001:10001` the directory and the file, matching the container user.

After cutover is confirmed, FenrirBot's stale copy is deleted along with the cog.

## FenrirBot-side removal

- `src/bot.py` — drop `"src.cogs.server_config"` from `INITIAL_COGS` (7 → 6).
- Delete `src/cogs/server_config.py`, `src/server_config/`, `tests/server_config/`,
  `specs/`.
- `Dockerfile` — drop `COPY specs/ ./specs/`.
- `requirements.txt` — drop **both** `ruamel.yaml` and `pydantic`. Verified: no module
  outside `server_config` imports either. `aiohttp` stays (`utils/grafana.py`,
  `utils/victoriametrics.py`, `utils/webhook_server.py`).
- `CLAUDE.md` — remove the `server_config` section.
- Discord: the stale `/server-config` commands disappear on the next tree sync.

Vault follow-up (not a code change): `2_Projects/FenrirBot/Cogs Reference.md` documents
seven cogs and a full `server_config` section; it needs updating, and the Librarian needs
its own project page. Handled via `vault-curator` after cutover.

## Cutover order

Both bots can be in the guild at once, but only one may own the reaction listeners.
FenrirBot keeps them until the Librarian is proven, so there is no window where a
reaction is dropped.

1. Build `librarian:latest`; migrate state; deploy the container.
2. Invite the Librarian: Manage Roles, Manage Channels, Manage Webhooks. Place its role
   **above** every role it manages — otherwise role writes fail with `Forbidden`.
3. Run `/server-config diff` from the Librarian against the live guild.
   **A no-op diff is the acceptance gate.** A non-empty diff means the lift changed
   behaviour — stop and investigate; do not `apply`.
4. Only then: remove the cog from FenrirBot, rebuild, `./scripts/start-docker.sh recreate management`.
5. Confirm a reaction-role still grants its role, now served by the Librarian.

Rollback at any point before step 4: stop the `librarian` container. FenrirBot is
untouched and still owns everything.

## Testing

- The four existing test files move unchanged and must pass under `pytest` in the new
  repo. Passing-on-arrival is the signal the lift was clean, not a skipped step.
- New tests, written first, for the genuinely new code:
  - `Config.from_env` raises without `DISCORD_TOKEN` and defaults `command_prefix`.
  - The `REPO_ROOT` guard still rejects `../` escapes and absolute paths from the new
    repo root.
  - `src/bot.py` loads exactly the one cog and the tree exposes the `/server-config` group.
- No test may `skip` when a fixture is missing — a missing input is a failure.

Together with the step-3 no-op diff, this is the whole regression gate.

## Out of scope

Deliberately not done, to keep this a pure extraction:

- Multi-guild support / per-guild specs.
- Bind-mounting the spec directory.
- Uploading a spec as a Discord attachment.
- Shrinking FenrirBot's own OAuth scopes (a natural follow-up, not part of this).
- Any refactor of `server_config` internals.

## Requires the user

Cannot be done from this session:

1. Create the Discord application + bot user; copy the token.
2. Enable the **Server Members Intent** in the developer portal.
3. Invite the bot to the guild with Manage Roles / Channels / Webhooks and position its
   role high enough.
4. Create the `Spifuth/the-librarian` repo (or approve `gh repo create`).

Once the token exists it goes to Infisical `apps` / `prod` as `LIBRARIAN_DISCORD_TOKEN`,
alongside `LIBRARIAN_IMAGE`, `LIBRARIAN_CPU`, `LIBRARIAN_MEM`.
