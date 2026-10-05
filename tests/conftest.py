import os

# src/config.py calls load_dotenv() at import time, and python-dotenv walks up
# from src/ until it finds a .env -- in a checkout that is the developer's real
# one, and in a worktree under .worktrees/ it is the main checkout's. Tests
# must never read it: set before any `src` module is imported.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import pytest

from src.utils import helpers


@pytest.fixture(autouse=True)
def unconfigured(monkeypatch):
    """Run every test as if no announcement channel or role were configured.

    A DISCORD_TOKEN exported in the shell would otherwise build a real Config
    and route announcements by its ids. Tests that need a configured channel
    or role patch `helpers.config` themselves.
    """
    monkeypatch.setattr(helpers, "config", None)
