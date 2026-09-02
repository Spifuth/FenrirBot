import asyncio
from dataclasses import dataclass, field

from src.server_config.applier import ApplyContext, apply_categories
from src.server_config.models import CategorySpec, OverwriteSpec, Spec
from src.server_config.reports import Summary
from src.server_config.resolver import Resolver


@dataclass
class FakeCategory:
    name: str
    position: int = 0
    edit_calls: list = field(default_factory=list)

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs)


@dataclass(unsafe_hash=True)
class FakeRole:
    name: str
    id: int = 1

    def is_default(self):
        return self.name == "@everyone"


@dataclass
class FakeGuild:
    categories: list = field(default_factory=list)
    roles: list = field(default_factory=list)

    @property
    def default_role(self):
        return FakeRole("@everyone", id=0)


def _ctx(guild, spec):
    resolver = Resolver(guild=guild, spec=spec)
    return ApplyContext(bot=None, guild=guild, spec=spec, resolver=resolver,
                        summary=Summary(), dry_run=False)


def _spec(categories):
    return Spec.model_construct(
        meta=None, server=None, roles=[], categories=categories,
        webhooks=[], reaction_roles=[],
    )


def test_category_without_overwrites_is_never_edited_with_an_empty_dict():
    existing = FakeCategory(name="General", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(id="c1", name="General", position=0, overwrites=[], channels=[])
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    wiping = [c for c in existing.edit_calls if c.get("overwrites") == {}]
    assert wiping == [], "an empty overwrites dict deletes every overwrite on the category"


def test_category_with_overwrites_still_reconciles_them():
    existing = FakeCategory(name="Staff", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(
        id="c1", name="Staff", position=0,
        overwrites=[OverwriteSpec(target="@everyone", deny=["VIEW_CHANNEL"])],
        channels=[],
    )
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    assert any("overwrites" in c and c["overwrites"] for c in existing.edit_calls)


def test_partial_overwrites_from_an_unresolved_role_do_not_apply():
    existing = FakeCategory(name="Staff", position=0)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(
        id="c1", name="Staff", position=0,
        overwrites=[OverwriteSpec(target="missing_role", allow=["VIEW_CHANNEL"])],
        channels=[],
    )
    spec = _spec([cat])
    ctx = _ctx(guild, spec)

    asyncio.run(apply_categories(ctx))

    wiping = [c for c in existing.edit_calls if c.get("overwrites") == {}]
    assert wiping == [], "a role that failed to resolve must not strip the live overwrites"
    assert ctx.summary.errors, "the unresolved target must be reported"


def test_position_changed_branch_also_refuses_an_empty_overwrites_dict():
    # The other guarded branch: when the category's position differs, edit() is
    # called with position= as well. An empty overwrites dict must still be
    # omitted rather than wiping the live config.
    existing = FakeCategory(name="General", position=3)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(id="c1", name="General", position=0, overwrites=[], channels=[])
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    assert existing.edit_calls, "the position change must still be applied"
    assert all("overwrites" not in c for c in existing.edit_calls), \
        "an empty overwrites dict deletes every overwrite on the category"
    assert existing.edit_calls[0]["position"] == 0


def test_position_changed_branch_still_applies_real_overwrites():
    existing = FakeCategory(name="Staff", position=3)
    guild = FakeGuild(categories=[existing])
    cat = CategorySpec(
        id="c1", name="Staff", position=0,
        overwrites=[OverwriteSpec(target="@everyone", deny=["VIEW_CHANNEL"])],
        channels=[],
    )
    spec = _spec([cat])

    asyncio.run(apply_categories(_ctx(guild, spec)))

    assert any(c.get("overwrites") for c in existing.edit_calls)
    assert existing.edit_calls[0]["position"] == 0
