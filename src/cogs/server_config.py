"""Slash commands for declarative server configuration."""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import ValidationError

from ..server_config.loader import load_spec
from ..server_config.differ import diff_roles, diff_categories, diff_channels
from ..server_config.reports import summary_from_diffs, render_embed, render_detail_file, Summary
from ..server_config.applier import (
    ApplyContext, apply_roles, apply_categories, apply_channels,
    apply_first_messages, apply_reaction_roles, apply_webhooks,
)
from ..server_config.resolver import Resolver
from ..server_config.state import load_state, save_state


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SPEC = "specs/server-spec.yaml"


class ServerConfigCog(commands.Cog, name="ServerConfig"):
    """Reconcile the guild against a YAML spec."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="server-config", description="Reconciliation déclarative du serveur")

    @group.command(name="validate", description="Valider une spec YAML sans rien modifier")
    @app_commands.describe(path="Chemin de la spec (défaut: specs/server-spec.yaml)")
    @app_commands.default_permissions(administrator=True)
    async def validate_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)):
            await interaction.response.send_message("❌ Chemin hors du repo refusé.", ephemeral=True)
            return
        if not spec_path.exists():
            await interaction.response.send_message(f"❌ Fichier introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.response.send_message(
                f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ Spec valide — {len(spec.roles)} rôle(s), "
            f"{len(spec.categories)} catégorie(s), "
            f"{sum(len(c.channels) for c in spec.categories)} salon(s), "
            f"{len(spec.webhooks)} webhook(s), "
            f"{len(spec.reaction_roles)} bloc(s) reaction-roles.",
            ephemeral=True,
        )

    @group.command(name="diff", description="Diff lisible: spec vs serveur actuel")
    @app_commands.describe(path="Chemin de la spec (défaut: specs/server-spec.yaml)")
    @app_commands.default_permissions(administrator=True)
    async def diff_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        await interaction.response.defer(ephemeral=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)) or not spec_path.exists():
            await interaction.followup.send(f"❌ Chemin invalide ou introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.followup.send(f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return

        rd = diff_roles(guild, spec.roles)
        cd = diff_categories(guild, spec.categories)
        chd = diff_channels(guild, spec.categories)
        summary = summary_from_diffs(rd, cd, chd)
        for r in rd.to_create:
            summary.detail_lines.append(f"+ role: {r.name}")
        for e in rd.to_edit:
            summary.detail_lines.append(f"~ role: {e.spec.name} ({', '.join(e.changed_fields)})")
        for c in cd.to_create:
            summary.detail_lines.append(f"+ category: {c.name}")
        for cat, ch in chd.to_create:
            summary.detail_lines.append(f"+ channel: {cat.name} / {ch.name}")
        await interaction.followup.send(
            embed=render_embed(summary, dry_run=True),
            file=render_detail_file(summary),
            ephemeral=True,
        )

    @group.command(name="apply", description="Appliquer la spec au serveur")
    @app_commands.describe(
        path="Chemin de la spec (défaut: specs/server-spec.yaml)",
        dry_run="Si True, log uniquement sans rien modifier (défaut: True)",
    )
    @app_commands.default_permissions(administrator=True)
    async def apply_cmd(
        self,
        interaction: discord.Interaction,
        path: str = DEFAULT_SPEC,
        dry_run: bool = True,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not str(spec_path).startswith(str(REPO_ROOT)) or not spec_path.exists():
            await interaction.followup.send(f"❌ Chemin invalide ou introuvable: `{path}`", ephemeral=True)
            return
        try:
            spec = load_spec(spec_path)
        except ValidationError as e:
            await interaction.followup.send(f"❌ Spec invalide:\n```\n{str(e)[:1800]}\n```", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return

        # Bot hierarchy warning: if bot isn't above the highest non-default role,
        # role create/edit of roles ranked above it will fail with Forbidden.
        # We don't abort — applier handles Forbidden per-role and reports as errors.
        me = guild.me
        if me is not None:
            highest_other = max((r.position for r in guild.roles if not r.is_default()), default=0)
            if me.top_role.position <= highest_other:
                await interaction.followup.send(
                    "⚠️ Le rôle du bot n'est pas au sommet de la hiérarchie. "
                    "Certaines opérations sur les rôles haut-classés peuvent échouer. "
                    "Best-effort en cours…",
                    ephemeral=True,
                )

        state = load_state()
        resolver = Resolver(guild=guild, spec=spec)
        summary = Summary()
        ctx = ApplyContext(
            bot=self.bot, guild=guild, spec=spec,
            resolver=resolver, summary=summary, dry_run=dry_run,
        )

        await apply_roles(ctx)
        await apply_categories(ctx)
        await apply_channels(ctx)
        first_msgs = await apply_first_messages(ctx)
        await apply_reaction_roles(ctx, first_messages=first_msgs, state=state)
        await apply_webhooks(ctx, state=state, invoker=interaction.user)

        if not dry_run:
            save_state(state)

        await interaction.followup.send(
            embed=render_embed(summary, dry_run=dry_run),
            file=render_detail_file(summary),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, added: bool):
        if payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return
        state = load_state()
        msg_entry = state.reaction_messages.get(payload.message_id)
        if not msg_entry:
            return
        emoji_key = str(payload.emoji)
        binding = msg_entry.bindings.get(emoji_key)
        if not binding:
            return

        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        role = guild.get_role(binding.role_id)
        if member is None or role is None:
            return

        try:
            if added:
                if role not in member.roles:
                    await member.add_roles(role, reason="server_config reaction-role")
            else:
                if binding.mode == "toggle" and role in member.roles:
                    await member.remove_roles(role, reason="server_config reaction-role toggle off")
                # add_only: do nothing on removal
        except discord.Forbidden:
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))
