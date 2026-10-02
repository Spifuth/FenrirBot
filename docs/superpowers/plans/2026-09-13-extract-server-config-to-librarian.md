# The Librarian — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift the `server_config` cog and its package out of FenrirBot into a standalone Discord bot, **The Librarian**, with no behaviour change.

**Architecture:** New repo `Spifuth/the-librarian` at `/srv/project/python/the-librarian/`, same `src/cogs/` + `src/utils/` + `src/server_config/` layout as FenrirBot so the lifted files need zero edits. One cog, no Docker access, no HTTP surface. Deployed as container `librarian` in the Nebula `apps` project.

**Tech Stack:** Python 3.12, `discord.py`, `pydantic`, `ruamel.yaml`, `python-dotenv`, `pytest`, Docker (alpine), Nebula compose + Infisical.

**Spec:** `docs/superpowers/specs/2026-09-13-extract-server-config-to-librarian.md` (this repo, same branch).

## Global Constraints

- **Source of truth for lifted files is FenrirBot at commit `7769780` (branch `dev`).** Copy byte-for-byte; do not reformat, rename, or "improve" during the lift.
- Python **3.12**. Container user **uid 10001**. Image tag **`librarian:latest`**.
- Repo is **private**, default branch `main`, integration branch `dev`. **All work in Tasks 1-5 happens on the branch `feat/lift-server-config`**, which PRs into `dev`. Only the repo-genesis placeholder commit touches `main` directly.
- Git identity for every commit: `-c user.name=Spifuth -c user.email=Github.spifuth@gmail.com`. Do not touch global git config.
- Discord-facing strings stay **French**; Python code, comments and docstrings stay **English**.
- **No secrets in the repo.** Config comes from env vars, injected by Infisical at deploy time.
- Every commit must pass the GitKeeper pre-commit hook. Do not use `--no-verify` in this plan.
- Tests must never `pytest.skip()` when an input is missing — a missing fixture is a failure.

---

### Task 1: Repo, scaffold, and the one piece of new runtime config

Creates the repository and everything that is not lifted code, plus `Config` — the only new runtime module with logic worth testing.

**Files:**
- Create: `/srv/project/python/the-librarian/` (new git repo)
- Create: `src/config.py`, `src/__init__.py`
- Create: `tests/__init__.py`, `tests/test_config.py`
- Create: `.gitignore`, `.gitkeeper.conf`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `cspell.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `src.config.Config` dataclass with fields `token: str`, `command_prefix: str = "!"`; classmethod `Config.from_env() -> Config` (raises `ValueError` when `DISCORD_TOKEN` is absent/empty); module-level singleton `config: Config | None`, which is `None` when `DISCORD_TOKEN` is unset.

- [ ] **Step 1: Create the GitHub repo and the local checkout**

```bash
gh repo create Spifuth/the-librarian --private \
  --description "The Librarian — declarative Discord server configuration, reconciled from a YAML spec"
mkdir -p /srv/project/python/the-librarian
cd /srv/project/python/the-librarian
git init -q -b main
git remote add origin https://github.com/Spifuth/the-librarian.git

# Repo genesis: main needs one commit before dev can branch from it, and dev
# before a feature branch can PR into it. Seed main with a placeholder, then
# do ALL of tasks 1-5 on the feature branch.
printf '# The Librarian\n' > README.md
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add README.md
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -q -m "chore: initial commit"
git branch dev
git checkout -q -b feat/lift-server-config dev
```

Every commit in Tasks 1-5 lands on `feat/lift-server-config`. `README.md` is
overwritten with its real content in Task 5.

- [ ] **Step 2: Copy repo hygiene files from FenrirBot verbatim**

```bash
cd /srv/project/python/the-librarian
F=/srv/project/python/FenrirBot
cp "$F/.gitignore" .gitignore
cp "$F/.gitkeeper.conf" .gitkeeper.conf
cp "$F/pytest.ini" pytest.ini
```

Then edit `.gitignore`: replace the four FenrirBot runtime-data lines with the Librarian's single one.

Remove:
```
data/containers.json
data/server_stats.json
data/server_config_state.json
data/open_incidents.json
```

Replace with:
```
data/server_config_state.json
```

- [ ] **Step 3: Write `requirements.txt` and `requirements-dev.txt`**

`requirements.txt` — note `docker` and the direct `aiohttp` pin are deliberately absent; `server_config` uses neither, and `aiohttp` still arrives transitively via discord.py:

```
discord.py>=2.3.0
python-dotenv>=1.0.0
pydantic>=2.6.0
ruamel.yaml>=0.18.0
```

`requirements-dev.txt`:

```
-r requirements.txt
pytest>=8.0.0
```

- [ ] **Step 4: Write `cspell.json`**

FenrirBot's word list is ~400 entries of French announcement copy the Librarian does not have. Start from the small subset that is actually used here:

```json
{
  "version": "0.2",
  "language": "en",
  "ignorePaths": ["venv/**", "data/**", "**/__pycache__/**"],
  "words": [
    "asyncio", "dotenv", "pathlib", "dataclasses", "ruamel", "pydantic",
    "cogs", "webhooks", "librarian", "Librarian",
    "Valider", "Appliquer", "Exporter", "Chemin", "serveur", "actuel",
    "lisible", "sommet", "hiérarchie", "Certaines", "opérations", "rôles",
    "haut", "classés", "peuvent", "échouer", "cours", "Commande",
    "utiliser", "dans", "invalide", "introuvable", "Identifiant",
    "existant", "défaut", "uniquement", "sans", "rien", "modifier",
    "Reconciliation", "déclarative", "Outils", "motifs"
  ]
}
```

- [ ] **Step 5: Write the failing test for `Config`**

Create `tests/__init__.py` (empty) and `tests/test_config.py`:

```python
"""Config is the only new runtime logic in the lift, so it gets real tests."""

import pytest

from src.config import Config


def test_from_env_raises_without_a_token(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Config.from_env()


def test_from_env_raises_when_the_token_is_empty(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "")
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Config.from_env()


def test_from_env_reads_the_token_and_defaults_the_prefix(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "a-token")
    monkeypatch.delenv("COMMAND_PREFIX", raising=False)
    cfg = Config.from_env()
    assert cfg.token == "a-token"
    assert cfg.command_prefix == "!"


def test_command_prefix_is_overridable(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "a-token")
    monkeypatch.setenv("COMMAND_PREFIX", "?")
    assert Config.from_env().command_prefix == "?"
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src'` (or `src.config`).

- [ ] **Step 7: Write `src/__init__.py` and `src/config.py`**

`src/__init__.py`:

```python
"""The Librarian - declarative Discord server configuration."""

__version__ = "1.0.0"
```

`src/config.py`:

```python
"""Bot configuration, loaded from environment variables.

The Librarian consumes no URLs and no API keys — only a Discord token. The
deployment injects it (Infisical → compose env), so there is nothing else to
read here.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    token: str
    command_prefix: str = "!"

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in environment variables")
        return cls(
            token=token,
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        )


config = Config.from_env() if os.getenv("DISCORD_TOKEN") else None
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest tests/test_config.py -q`
Expected: PASS, 4 passed.

- [ ] **Step 9: Install the GitKeeper hooks, then commit**

```bash
cd /srv/project/python/the-librarian
gitkeeper install-hooks
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "feat: scaffold the repo and the env-backed Config

The Librarian takes one env var, DISCORD_TOKEN, and nothing else — no URLs,
no API keys. Config.from_env() refuses an absent or empty token rather than
booting into a confusing Discord login failure.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

Expected: GitKeeper prints `4 passed` / `✓ All checks passed`, then the commit succeeds.

---

### Task 2: Lift `server_config` verbatim and prove the existing tests still pass

The heart of the extraction. Nothing is rewritten; the acceptance signal is that FenrirBot's own test suite passes unchanged in the new repo.

**Files:**
- Create: `src/server_config/` (10 files, copied), `src/cogs/server_config.py` (copied), `src/utils/permissions.py` (copied), `specs/server-spec.yaml` (copied)
- Create: `src/cogs/__init__.py`, `src/utils/__init__.py`, `tests/server_config/__init__.py`
- Create: `tests/server_config/` (5 files, copied)
- Create: `tests/test_repo_root_guard.py`

**Interfaces:**
- Consumes: `src.config` from Task 1 (not imported by these files, but they share the package).
- Produces: `src.cogs.server_config.ServerConfigCog` with `async def setup(bot)`; module constants `REPO_ROOT: pathlib.Path` and `DEFAULT_SPEC: str = "specs/server-spec.yaml"`; `src.utils.permissions.admin_only()`.

- [ ] **Step 1: Copy the files byte-for-byte**

```bash
cd /srv/project/python/the-librarian
F=/srv/project/python/FenrirBot
mkdir -p src/cogs src/utils tests/server_config
cp -r "$F/src/server_config" src/server_config
cp "$F/src/cogs/server_config.py" src/cogs/server_config.py
cp "$F/src/utils/permissions.py" src/utils/permissions.py
cp -r "$F/specs" specs
cp "$F/tests/server_config/"*.py tests/server_config/
```

- [ ] **Step 2: Write the two package `__init__.py` files**

FenrirBot's `src/cogs/__init__.py` and `src/utils/__init__.py` eagerly import its other cogs and utils. Those do not exist here, so write fresh minimal ones rather than copying.

`src/cogs/__init__.py`:

```python
"""The Librarian cogs (command modules)."""
```

`src/utils/__init__.py`:

```python
"""Utility modules for The Librarian."""
```

`tests/server_config/__init__.py` is empty — FenrirBot's copy is already a 0-byte file and was copied in Step 1. Verify it exists:

```bash
test -f tests/server_config/__init__.py && echo present
```

- [ ] **Step 3: Verify the copies are byte-identical to the source**

This is the whole premise of the task, so check it rather than assume it.

```bash
cd /srv/project/python/the-librarian
F=/srv/project/python/FenrirBot
diff -r "$F/src/server_config" src/server_config && echo "server_config OK"
diff "$F/src/cogs/server_config.py" src/cogs/server_config.py && echo "cog OK"
diff "$F/src/utils/permissions.py" src/utils/permissions.py && echo "permissions OK"
diff "$F/specs/server-spec.yaml" specs/server-spec.yaml && echo "spec OK"
```

Expected: four `OK` lines, no diff output.

- [ ] **Step 4: Run the lifted test suite**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest -q`
Expected: PASS. The four lifted files contribute their tests plus Task 1's four, all green, zero collection errors.

If anything fails, **stop**: the lift changed behaviour and the cause must be found before continuing. Do not edit the lifted files to make tests pass.

- [ ] **Step 5: Write the failing test for the re-anchored path guard**

`REPO_ROOT` is computed from `__file__`, so it re-anchors to the new repo for free. That is an assumption worth a test. Create `tests/test_repo_root_guard.py`:

```python
"""The spec path is attacker-controllable (a slash-command argument), so the
containment guard is re-verified against this repo's root, not FenrirBot's."""

from pathlib import Path

from src.cogs.server_config import DEFAULT_SPEC, REPO_ROOT


def test_repo_root_is_this_repo():
    assert (REPO_ROOT / "src" / "cogs" / "server_config.py").is_file()
    assert (REPO_ROOT / "pytest.ini").is_file()


def test_the_default_spec_resolves_inside_the_repo():
    resolved = (REPO_ROOT / DEFAULT_SPEC).resolve()
    assert resolved.is_relative_to(REPO_ROOT)
    assert resolved.is_file()


def test_parent_traversal_is_rejected():
    resolved = (REPO_ROOT / "../../../etc/passwd").resolve()
    assert not resolved.is_relative_to(REPO_ROOT)


def test_an_absolute_path_escapes_and_is_rejected():
    # (REPO_ROOT / "/etc/passwd") discards REPO_ROOT — pathlib treats an
    # absolute right-hand side as replacing the left. The guard must catch it.
    resolved = (REPO_ROOT / "/etc/passwd").resolve()
    assert not resolved.is_relative_to(REPO_ROOT)
```

- [ ] **Step 6: Run it**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest tests/test_repo_root_guard.py -q`
Expected: PASS — 4 passed. These assert behaviour the lifted code already has; passing on arrival is the information, confirming `REPO_ROOT` followed the files.

- [ ] **Step 7: Commit**

```bash
cd /srv/project/python/the-librarian
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "feat: lift server_config out of FenrirBot, unchanged

The package, the cog, its spec and its tests move byte-for-byte. The two
relative imports (..utils.permissions, ..server_config.*) resolve because the
layout is identical, and REPO_ROOT is computed from __file__ so the spec-path
containment guard re-anchors to this repo with no edit.

admin_only() is copied rather than moved — seven FenrirBot cogs still use it.

FenrirBot's test suite passes here unchanged, which is the signal that the
lift changed nothing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Bot entry point

**Files:**
- Create: `src/bot.py`, `run.py`
- Create: `tests/test_bot.py`

**Interfaces:**
- Consumes: `src.config.config`, `src.cogs.server_config`.
- Produces: `src.bot.Librarian(commands.Bot)` with class attribute `INITIAL_COGS: list[str]`; `src.bot.create_bot() -> Librarian`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bot.py`:

```python
"""The bot wiring is new code: one cog, and three intents chosen deliberately."""

from src.bot import Librarian, create_bot


def test_loads_exactly_the_server_config_cog():
    assert Librarian.INITIAL_COGS == ["src.cogs.server_config"]


def test_intents_are_the_three_the_cog_needs():
    bot = create_bot()
    assert bot.intents.guilds is True
    assert bot.intents.members is True
    assert bot.intents.reactions is True


def test_message_content_intent_is_not_requested():
    # server_config never reads message text. Asking for a privileged intent
    # it does not use is a permission the bot should not hold.
    assert create_bot().intents.message_content is False


def test_create_bot_returns_a_librarian():
    assert isinstance(create_bot(), Librarian)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest tests/test_bot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.bot'`.

- [ ] **Step 3: Write `src/bot.py`**

```python
"""The Librarian - main bot class and initialization."""

import logging

import discord
from discord.ext import commands

from .config import config

log = logging.getLogger(__name__)


class Librarian(commands.Bot):
    """Reconciles a Discord guild against a declarative YAML spec."""

    INITIAL_COGS = [
        "src.cogs.server_config",
    ]

    def __init__(self) -> None:
        # guilds comes from Intents.default(). members is needed because the
        # reaction-role listeners resolve a Member to add a role to, and
        # reactions delivers the raw reaction events themselves.
        # message_content is deliberately NOT requested: this bot never reads
        # message text, and it is a privileged intent.
        intents = discord.Intents.default()
        intents.members = True
        intents.reactions = True

        super().__init__(
            command_prefix=config.command_prefix if config else "!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        for cog in self.INITIAL_COGS:
            try:
                await self.load_extension(cog)
                log.info("Loaded cog: %s", cog)
            except Exception as e:  # noqa: BLE001
                log.error("Failed to load %s: %s", cog, e)

        try:
            synced = await self.tree.sync()
            log.info("Synced %d slash command(s)", len(synced))
        except Exception as e:  # noqa: BLE001
            log.error("Failed to sync commands: %s", e)

    async def on_ready(self) -> None:
        log.info("The Librarian is online! user=%s guilds=%d", self.user, len(self.guilds))


def create_bot() -> Librarian:
    return Librarian()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest tests/test_bot.py -q`
Expected: PASS, 4 passed.

- [ ] **Step 5: Write `run.py`**

```python
#!/usr/bin/env python3
"""The Librarian - entry point."""

import logging
import sys

from src.bot import create_bot
from src.config import config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not config:
        print("❌ DISCORD_TOKEN manquant. Le définir dans l'environnement (voir README).")
        sys.exit(1)
    print("📚 Démarrage de The Librarian...")
    bot = create_bot()
    bot.run(config.token)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the entry point refuses to start without a token**

Run: `cd /srv/project/python/the-librarian && env -u DISCORD_TOKEN python3 run.py; echo "exit=$?"`
Expected: prints the `DISCORD_TOKEN manquant` line and `exit=1`.

- [ ] **Step 7: Run the whole suite and commit**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest -q`
Expected: PASS, all tests green.

```bash
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "feat: bot entry point, one cog, three intents

INITIAL_COGS is an explicit one-element list rather than pkgutil discovery —
with a single cog, discovery hides more than it saves.

message_content is deliberately not requested. FenrirBot needs it; this bot
never reads message text, so it drops a privileged intent on the way out.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Container image and build script

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `build.sh`

**Interfaces:**
- Consumes: `run.py`, `src/`, `specs/`, `requirements.txt`.
- Produces: local image `librarian:latest`, entrypoint `python run.py`, running as uid 10001 with a writable `/app/data`.

- [ ] **Step 1: Write the `Dockerfile`**

```dockerfile
# ═══════════════════════════════════════════════════════════════
# THE LIBRARIAN - Discord Bot
# Declarative server configuration, reconciled from a YAML spec
# ═══════════════════════════════════════════════════════════════

FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code. specs/ is baked in on purpose: the YAML is the source of
# truth for the guild and stays git-versioned, so changing it is a rebuild.
COPY src/ ./src/
COPY specs/ ./specs/
COPY run.py .

# Run as an unprivileged user. This process holds the Discord token and has
# Manage Roles/Channels/Webhooks on the guild.
# NOTE: the host bind mount at ${DOCKERDIR}/appdata/librarian/data must be
# chowned to 10001:10001 or the bot cannot persist reaction-role bindings.
RUN adduser -D -u 10001 librarian \
    && mkdir -p /app/data \
    && chown -R librarian:librarian /app

USER librarian

CMD ["python", "run.py"]
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git/
.github/
.worktrees/
tests/
docs/
venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
data/
.env
```

- [ ] **Step 3: Write `build.sh`**

```bash
#!/usr/bin/env bash
# Build librarian:latest Docker image locally.
# Run this after code changes, then restart via the nebula stack.
#
# Usage:
#   ./build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "▶ Building librarian:latest ..."
docker build --pull -t librarian:latest .
echo "✓ librarian:latest built"

echo ""
echo "Done. To deploy:"
echo "  cd /srv/nebula && ./scripts/start-docker.sh up apps"
```

Then: `chmod +x build.sh`

- [ ] **Step 4: Build the image**

Run: `cd /srv/project/python/the-librarian && ./build.sh`
Expected: build succeeds, ends with `✓ librarian:latest built`.

- [ ] **Step 5: Verify the image refuses to start without a token, as the right user**

```bash
docker run --rm librarian:latest python -c "import os; print('uid', os.getuid())"
docker run --rm librarian:latest; echo "exit=$?"
docker run --rm librarian:latest python -c "from src.cogs.server_config import REPO_ROOT, DEFAULT_SPEC; print((REPO_ROOT / DEFAULT_SPEC).is_file())"
```

Expected: `uid 10001`; then the `DISCORD_TOKEN manquant` message with `exit=1`; then `True` — proving the spec is baked in and the guard anchors at `/app`.

- [ ] **Step 6: Commit**

```bash
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "build: alpine image and local build script, FenrirBot pattern

Runs as uid 10001. specs/ is baked into the image deliberately — the YAML is
the source of truth for the guild, so a change to it should be a reviewable
commit and a rebuild, not an edit on a mounted volume.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: CI, documentation, and the first PR

**Files:**
- Create: `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `dev` branch on the remote; a PR from a feature branch into `dev`.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

Copied from FenrirBot, which already has the shape the estate uses:

```yaml
name: CI

on:
  push:
    branches: [dev]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: pytest -q

  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Critical rules (blocking)
        run: pipx run ruff check --select=E9,F63,F7,F82 .
      - name: Full style (advisory)
        run: pipx run ruff check .
        continue-on-error: true
```

- [ ] **Step 2: Do NOT add a `.env.example`**

Deliberately omitted. GitKeeper's `forbid_files` pattern `(^|/)\.env\..*` blocks the
file at **commit** time, and the fix for that is an open policy decision tracked in the
vault's Open Threads. Seeding a brand-new repo with a file that cannot be committed
without `--no-verify` would bake the bypass into the project's first day.

The bot takes exactly two env vars and both are documented in `README.md` and
`CLAUDE.md`. Add `.env.example` once the `forbid_files` pattern is narrowed.

- [ ] **Step 3: Write `README.md`**

````markdown
# 📚 The Librarian

Discord bot that reconciles a server against a **declarative YAML spec** — roles,
categories, channels, first messages, reaction roles and webhooks.

The spec (`specs/server-spec.yaml`) is the source of truth. The bot diffs it against
the live guild and applies the difference.

## Commands

All commands are admin-gated, both in the Discord UI and at invocation time.

| Command | Effect |
|---|---|
| `/server-config validate [path]` | Validate a spec without touching the server |
| `/server-config diff [path]` | Readable diff: spec vs. current server |
| `/server-config apply [path] [dry_run]` | Apply the spec — **`dry_run` defaults to `True`** |
| `/server-config export [output]` | Export the current server as YAML |
| `/server-config webhooks reveal <id>` | Re-DM an existing webhook URL by its YAML id |

> `/server-config apply` changes nothing unless you pass `dry_run:False`.

## Requirements

The bot needs **Manage Roles**, **Manage Channels** and **Manage Webhooks**, and its
role must sit **above** every role it manages — Discord refuses edits to roles ranked
above the actor. The `apply` command warns when this is not the case and continues
best-effort rather than aborting.

The **Server Members Intent** must be enabled in the Discord developer portal, or the
reaction-role listeners cannot resolve a member.

## State

`data/server_config_state.json` holds reaction-message bindings and webhook id →
Discord webhook mappings. **It is not reproducible from the spec** — a lost webhook
token cannot be re-read from Discord. Back it up.

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest -q
python run.py
```

## Deployment

Built locally, not published to a registry:

```bash
./build.sh
cd /srv/nebula && ./scripts/start-docker.sh recreate librarian
```

## History

Extracted from [FenrirBot](https://github.com/Spifuth/FenrirBot) in September 2026.
FenrirBot is a homelab-ops bot; guild configuration is a different domain, and the
code was already self-contained enough to move without a rewrite.
````

- [ ] **Step 4: Write `CLAUDE.md`**

````markdown
# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest -q       # tests
python run.py              # run locally
./build.sh                 # build librarian:latest
cd /srv/nebula && ./scripts/start-docker.sh recreate librarian
```

CI runs `pytest` plus `ruff` on every pull request and on pushes to `dev`.

## Architecture

`run.py` → `src/bot.py:create_bot()` → `Librarian.setup_hook()` (loads the one cog,
syncs the command tree) → `on_ready()`.

- **`src/config.py`** — `Config` dataclass, one required env var (`DISCORD_TOKEN`).
  Module-level `config` singleton is `None` when the token is absent.
- **`src/bot.py`** — `Librarian(commands.Bot)`. `INITIAL_COGS` is an explicit list.
  Intents: `guilds`, `members`, `reactions`. **Not `message_content`.**
- **`src/cogs/server_config.py`** — the `/server-config` command group plus the
  `on_raw_reaction_add` / `on_raw_reaction_remove` listeners.
- **`src/server_config/`** — the engine: `loader`, `models` (pydantic), `permissions`,
  `differ`, `resolver`, `applier`, `exporter`, `reports`, `state`.
- **`specs/server-spec.yaml`** — the declarative input. Baked into the image.
- **`data/server_config_state.json`** — runtime state. Bind-mounted in production.

## Conventions

- Discord-facing strings are **French**; code, comments and docstrings are **English**.
- Feature branches PR into **`dev`**. `main` is release-only.
- The spec path is user-supplied, so it is resolved and rejected unless
  `is_relative_to(REPO_ROOT)`. Do not loosen that guard.
- `apply` defaults to `dry_run=True`. Keep it that way.
````

- [ ] **Step 5: Run the full suite one more time**

Run: `cd /srv/project/python/the-librarian && python3 -m pytest -q`
Expected: PASS, everything green.

- [ ] **Step 6: Commit, create `dev`, push both branches**

```bash
cd /srv/project/python/the-librarian
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "docs: README, CLAUDE.md, CI workflow and env template

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push origin main
git push origin dev
git push -u origin feat/lift-server-config
gh pr create --base dev --head feat/lift-server-config \
  --title "feat: The Librarian — server_config lifted out of FenrirBot" \
  --body "Extraction per docs/superpowers/specs/2026-09-13-extract-server-config-to-librarian.md in the FenrirBot repo. FenrirBot's server_config test suite passes here unchanged, which is the signal the lift changed nothing. Deployment and cutover are Task 6, blocked on a Discord bot token."
```

- [ ] **Step 7: Report the deployment prerequisites**

Task 6 cannot start without these, and only the user can do them. State them plainly and stop:

1. Create the Discord application + bot user; copy the token.
2. Enable the **Server Members Intent** in the developer portal.
3. Invite the bot with Manage Roles / Channels / Webhooks, and position its role above every role in the spec.

---

### Task 6: Nebula deployment and cutover — BLOCKED on Task 5's prerequisites

Do not start until the user confirms the Discord bot exists and the token is available.

**Files:**
- Create: `/srv/nebula/docker/services/apps/librarian/librarian.yml`
- Modify: `/srv/nebula/projects/apps/` compose include (follow the existing `lycee-bot` entry)

**Interfaces:**
- Consumes: image `librarian:latest`; Infisical `apps`/`prod` vars `LIBRARIAN_DISCORD_TOKEN`, `LIBRARIAN_IMAGE`, `LIBRARIAN_CPU`, `LIBRARIAN_MEM`.
- Produces: running container `librarian`.

- [ ] **Step 1: Push the Infisical secrets**

```bash
source /srv/nebula/.infisical-auth
INFISICAL_TOKEN="$INFISICAL_ACCESS_TOKEN" infisical secrets set \
  LIBRARIAN_DISCORD_TOKEN="<token>" \
  LIBRARIAN_IMAGE="librarian:latest" \
  LIBRARIAN_CPU="0.25" \
  LIBRARIAN_MEM="256M" \
  --projectId ae5d41a7-c8e7-4088-87fe-21be2f194c76 \
  --domain "$INFISICAL_DOMAIN" \
  --env prod
```

`--env prod` is not optional. Omitting it writes to `dev`, the values are never injected, and the failure is a silent blank string.

- [ ] **Step 2: Migrate the state file — do this before the first boot**

```bash
mkdir -p /srv/nebula/docker/appdata/librarian/data
cp /srv/nebula/docker/appdata/fenrirbot/data/server_config_state.json \
   /srv/nebula/docker/appdata/librarian/data/server_config_state.json
chown -R 10001:10001 /srv/nebula/docker/appdata/librarian/data
```

`cp`, not `mv` — FenrirBot keeps its copy as the rollback path until cutover is proven.

Verify the content survived:

```bash
python3 -c "import json; d=json.load(open('/srv/nebula/docker/appdata/librarian/data/server_config_state.json')); print({k: len(v) for k, v in d.items()})"
```

Expected: `{'webhooks': 1, 'reaction_messages': 4}` — matching FenrirBot's copy. If the counts differ, stop.

- [ ] **Step 3: Write the compose service**

`/srv/nebula/docker/services/apps/librarian/librarian.yml`:

```yaml
services:
  librarian:
    image: ${LIBRARIAN_IMAGE}
    container_name: librarian
    labels:
      - "diun.enable=false"
    security_opt:
      - no-new-privileges:true
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '${LIBRARIAN_CPU}'
          memory: ${LIBRARIAN_MEM}
        reservations:
          cpus: '0.05'
          memory: 64M
    networks:
      - default
    volumes:
      - ${DOCKERDIR}/appdata/librarian/data:/app/data
    environment:
      TZ: ${TZ}
      DISCORD_TOKEN: ${LIBRARIAN_DISCORD_TOKEN}
```

Only `default`. No `socket_proxy` — the bot has no Docker access. No `t3_proxy` — it has no HTTP surface, so it needs no Traefik route.

- [ ] **Step 4: Deploy**

```bash
cd /srv/nebula && ./scripts/start-docker.sh up apps
```

Never plain `docker compose` — `start-docker.sh` is what injects the Infisical secrets.

- [ ] **Step 5: Verify it booted and the state was read**

```bash
docker ps --filter name=librarian --format '{{.Names}}\t{{.Status}}'
docker logs librarian --tail 30
```

Expected: `Up`, a `Loaded cog: src.cogs.server_config` line, a `Synced N slash command(s)` line, and `The Librarian is online!`.

- [ ] **Step 6: THE ACCEPTANCE GATE — run `/server-config diff` from the Librarian**

In Discord, as an admin, run `/server-config diff`.

Expected: **a no-op diff** — no roles, categories or channels to create, edit or delete.

A non-empty diff means the lift changed behaviour. **Stop. Do not run `apply`. Do not remove the cog from FenrirBot.** Investigate first.


> **Do not leave both bots running overnight.** Once the state file is migrated, the
> Librarian and FenrirBot hold the *same* reaction bindings, so `on_raw_reaction_add`
> fires in both. `_handle_reaction` guards with `if role not in member.roles` (and the
> mirror on removal), so the second call is a no-op rather than an error — but it is
> still a duplicate Discord API call and a duplicate audit-log entry every time someone
> reacts. The overlap is deliberate (it means no reaction is ever *dropped*), but keep it
> to minutes: if the diff is clean, go straight to Step 7.

- [ ] **Step 7: Only now, remove the cog from FenrirBot**

On branch `refactor/extract-server-config` in `/srv/project/python/FenrirBot`:

```bash
cd /srv/project/python/FenrirBot
git rm -r --quiet src/server_config tests/server_config specs
git rm --quiet src/cogs/server_config.py
```

Then edit:
- `src/bot.py` — delete the `"src.cogs.server_config",` line from `INITIAL_COGS` (7 → 6).
- `Dockerfile` — delete the `COPY specs/ ./specs/` line.
- `requirements.txt` — delete **both** `pydantic>=2.6.0` and `ruamel.yaml>=0.18.0`. Verified 2026-09-13: no module outside `server_config` imports either. Keep `aiohttp` (`utils/grafana.py`, `utils/victoriametrics.py`, `utils/webhook_server.py`).
- `.gitignore` — delete the `data/server_config_state.json` line.
- `CLAUDE.md` — delete the `server_config.py` bullet from the Cogs list and the `data/server_config_state.json` bullet from the persistent-data list.

- [ ] **Step 8: Verify FenrirBot still passes and still builds**

```bash
cd /srv/project/python/FenrirBot
python3 -m pytest -q
grep -c "src.cogs" src/bot.py
./build.sh
```

Expected: tests pass (the `server_config` tests are gone; the rest remain green), the cog list has 6 entries, the image builds.

- [ ] **Step 9: Redeploy FenrirBot and confirm six cogs**

```bash
cd /srv/nebula && ./scripts/start-docker.sh recreate fenrirbot
docker logs fenrirbot --tail 20
```

Expected: six `Loaded:` lines, no `server_config`. In Discord, `/server-config` now resolves to the Librarian only.

- [ ] **Step 10: Delete FenrirBot's now-stale state copy and commit**

```bash
rm /srv/nebula/docker/appdata/fenrirbot/data/server_config_state.json
cd /srv/project/python/FenrirBot
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com add -A
git -c user.name=Spifuth -c user.email=Github.spifuth@gmail.com commit -m "refactor: remove server_config — it lives in The Librarian now

Seven cogs to six. Drops pydantic and ruamel.yaml (server_config was their
only consumer) and the specs/ COPY from the image.

Cutover was gated on a no-op /server-config diff from the Librarian against
the live guild, run before this removal, with the reaction-role and webhook
state migrated first.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 11: Open the FenrirBot PR into `dev`**

```bash
cd /srv/project/python/FenrirBot
git push origin refactor/extract-server-config
gh pr create --base dev --head refactor/extract-server-config \
  --title "refactor: extract server_config into The Librarian"
```

- [ ] **Step 12: Record it in the vault**

Use the `vault-curator` skill (Mode A): create `2_Projects/The Librarian/` with a main page following the project conventions, and update `2_Projects/FenrirBot/Cogs Reference.md` — it currently documents seven cogs and a full `server_config` section that no longer belongs there.
