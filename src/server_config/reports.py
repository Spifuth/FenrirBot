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
