"""Minimal stand-ins for the discord.py objects the cogs touch.

Only the attributes and coroutines a cog actually calls exist here. Every
REST-shaped call (send, defer, edit, create_thread, add_reaction) is appended
to one shared CallLog, so a test can assert on the exact sequence a command
or button produces, without a gateway connection or an HTTP client.

Command callbacks are invoked through `Command.callback(cog, interaction, ...)`,
which skips discord.py's check machinery on purpose: the admin gate is pinned
separately in test_permission_gate.py.
"""

import discord


class CallLog(list):
    """Ordered record of (call_name, kwargs) tuples."""

    def names(self) -> list[str]:
        return [name for name, _ in self]

    def of(self, name: str) -> list[dict]:
        return [kwargs for n, kwargs in self if n == name]


class FakeUser:
    def __init__(self, user_id: int = 1, display_name: str = "Spifuth"):
        self.id = user_id
        self.display_name = display_name
        self.mention = f"<@{user_id}>"


class FakeThread:
    def __init__(self, log: CallLog, thread_id: int = 9001):
        self.log = log
        self.id = thread_id
        self.mention = f"<#{thread_id}>"

    async def send(self, content=None, **kwargs):
        self.log.append(("thread.send", {"content": content, **kwargs}))

    async def edit(self, **kwargs):
        self.log.append(("thread.edit", kwargs))


class FakeMessage:
    def __init__(self, log: CallLog, message_id: int = 4242, content: str = "",
                 thread: FakeThread | None = None):
        self.log = log
        self.id = message_id
        self.content = content
        self.thread = thread or FakeThread(log)

    async def edit(self, **kwargs):
        self.log.append(("message.edit", kwargs))

    async def create_thread(self, **kwargs):
        self.log.append(("message.create_thread", kwargs))
        return self.thread

    async def reply(self, content=None, **kwargs):
        self.log.append(("message.reply", {"content": content, **kwargs}))

    async def add_reaction(self, emoji):
        self.log.append(("message.add_reaction", {"emoji": emoji}))


class FakeChannel(discord.abc.Messageable):
    """A Messageable, so the cog's isinstance guard treats it as sendable."""

    def __init__(self, log: CallLog, channel_id: int = 2, message: FakeMessage | None = None):
        self.log = log
        self.id = channel_id
        self.message = message or FakeMessage(log)

    async def _get_channel(self):  # required by the Messageable ABC
        return self

    async def send(self, content=None, **kwargs):
        self.log.append(("channel.send", {"channel": self.id, "content": content, **kwargs}))
        return self.message


class FakeResponse:
    def __init__(self, log: CallLog):
        self.log = log
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content=None, **kwargs):
        self._done = True
        self.log.append(("response.send_message", {"content": content, **kwargs}))

    async def defer(self, **kwargs):
        self._done = True
        self.log.append(("response.defer", kwargs))


class FakeFollowup:
    def __init__(self, log: CallLog):
        self.log = log

    async def send(self, content=None, **kwargs):
        self.log.append(("followup.send", {"content": content, **kwargs}))


class FakeInteraction:
    def __init__(self, user: FakeUser | None = None, channel_id: int = 2,
                 message: FakeMessage | None = None):
        self.log = CallLog()
        self.user = user or FakeUser()
        self.channel = FakeChannel(self.log, channel_id=channel_id)
        self.response = FakeResponse(self.log)
        self.followup = FakeFollowup(self.log)
        self.message = message
        self.command = None


class FakeContext:
    """Prefix-command context: channel, author and the invoking message."""

    def __init__(self, author: FakeUser | None = None):
        self.log = CallLog()
        self.author = author or FakeUser()
        self.channel = FakeChannel(self.log)
        self.message = FakeMessage(self.log, message_id=1)


class FakeBot:
    def __init__(self, channels: dict | None = None, users: dict | None = None,
                 latency: float = 0.0, fetch_user_error: Exception | None = None):
        self.channels = channels or {}
        self.users = users or {}
        self.latency = latency
        self.fetch_user_error = fetch_user_error
        self.fetched: list[int] = []

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_user(self, user_id):
        return self.users.get(user_id)

    async def fetch_user(self, user_id):
        self.fetched.append(user_id)
        if self.fetch_user_error is not None:
            raise self.fetch_user_error
        return FakeUser(user_id, display_name=f"fetched-{user_id}")


class FakeIncidentStore:
    """Records what a cog or view asks the incident store to do."""

    def __init__(self, raise_on: set[str] = frozenset()):
        self.raise_on = raise_on
        self.added: list = []
        self.removed: list[int] = []
        self.removed_services: list[str] = []

    def add(self, record):
        if "add" in self.raise_on:
            raise PermissionError("read-only data dir")
        self.added.append(record)

    def remove(self, message_id):
        self.removed.append(message_id)

    def remove_by_service(self, service):
        if "remove_by_service" in self.raise_on:
            raise PermissionError("read-only data dir")
        self.removed_services.append(service)
        return 1


def field(embed: discord.Embed, name: str) -> str:
    """The value of the embed field called `name`; fails loudly if absent."""
    for f in embed.fields:
        if f.name == name:
            return f.value
    raise AssertionError(f"no field {name!r} in {[f.name for f in embed.fields]}")
