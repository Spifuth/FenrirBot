"""Apply a Spec to a discord.Guild. Supports dry_run.

All write operations go through helpers that no-op in dry_run mode and append
a `[DRY]`-prefixed line to the report.
"""

from __future__ import annotations

from dataclasses import dataclass

import discord

from .differ import diff_roles
from .models import Spec, RoleSpec, CategorySpec, ChannelSpec, OverwriteSpec, ChannelType
from .permissions import to_permissions, to_permission_overwrite
from .reports import Summary
from .resolver import Resolver
from .state import State, ReactionMessageEntry, ReactionBindingEntry, WebhookEntry


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
        except (discord.Forbidden, discord.HTTPException) as e:
            ctx.err(
                "role reposition skipped: move the bot role to the top of the "
                f"server hierarchy to enable reordering ({e})"
            )


def _build_overwrites(
    ctx: ApplyContext, overwrites: list[OverwriteSpec]
) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
    out: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}
    for ow in overwrites:
        target = ctx.resolver.resolve_target(ow.target)
        if target is None:
            if not ctx.dry_run:
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
        if "COMMUNITY" not in ctx.guild.features:
            ctx.err(
                f"channel {ch_spec.name}: type=announcement requires the guild to "
                "have COMMUNITY enabled — created as a regular text channel instead"
            )
            return await ctx.guild.create_text_channel(
                topic=ch_spec.topic or None,
                slowmode_delay=ch_spec.slowmode_delay,
                **common,
            )
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
        if "COMMUNITY" not in ctx.guild.features:
            ctx.err(
                f"channel {ch_spec.name}: type=forum requires the guild to have "
                "COMMUNITY enabled — created as a regular text channel instead"
            )
            return await ctx.guild.create_text_channel(
                topic=ch_spec.topic or None,
                **common,
            )
        return await ctx.guild.create_forum(
            topic=ch_spec.topic or None,
            **common,
        )
    ctx.err(f"unknown channel type for {ch_spec.name}: {ch_spec.type}")
    return None


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
    if bot_user is None:
        ctx.err("bot.user is None — bot may be reconnecting")
        return {}
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
        ctx.log(f"+ webhook: {wh_spec.name} (id={new.id}, url={_mask_webhook_url(new.url)})")
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
