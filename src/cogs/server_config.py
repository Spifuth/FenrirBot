"""Slash commands for declarative server configuration."""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import ValidationError

from ..server_config.loader import load_spec
from ..server_config.exporter import export_guild
from ..server_config.differ import diff_roles, diff_categories, diff_channels
from ..server_config.reports import summary_from_diffs, render_embed, render_detail_file, Summary
from ..server_config.applier import (
    ApplyContext, apply_roles, apply_categories, apply_channels,
    apply_first_messages, apply_reaction_roles, apply_webhooks,
)
from ..server_config.resolver import Resolver
from ..server_config.state import load_state, save_state
from ..utils.permissions import admin_only


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SPEC = "specs/server-spec.yaml"


class ServerConfigCog(commands.Cog, name="ServerConfig"):
    """Reconcile the guild against a YAML spec."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="server-config", description="Reconciliation déclarative du serveur")

    webhooks_group = app_commands.Group(
        parent=group, name="webhooks", description="Outils webhooks"
    )

    @group.command(name="validate", description="Valider une spec YAML sans rien modifier")
    @app_commands.describe(path="Chemin de la spec (défaut: specs/server-spec.yaml)")
    @admin_only()
    async def validate_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        spec_path = (REPO_ROOT / path).resolve()
        if not spec_path.is_relative_to(REPO_ROOT):
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
    @admin_only()
    async def diff_cmd(self, interaction: discord.Interaction, path: str = DEFAULT_SPEC):
        await interaction.response.defer(ephemeral=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not spec_path.is_relative_to(REPO_ROOT) or not spec_path.exists():
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
    @admin_only()
    async def apply_cmd(
        self,
        interaction: discord.Interaction,
        path: str = DEFAULT_SPEC,
        dry_run: bool = True,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        spec_path = (REPO_ROOT / path).resolve()
        if not spec_path.is_relative_to(REPO_ROOT) or not spec_path.exists():
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

        # Bot hierarchy warning: if bot isn't above the highest non-default,
        # non-bot-owned role, role create/edit/reposition of roles ranked above
        # it will fail with Forbidden. Applier handles Forbidden per-role.
        me = guild.me
        if me is not None:
            my_role_ids = {r.id for r in me.roles}
            highest_other = max(
                (r.position for r in guild.roles
                 if not r.is_default() and r.id not in my_role_ids),
                default=0,
            )
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
            # Discord has already been mutated at this point. If the state file
            # cannot be written the webhook/reaction-role bindings are lost, so
            # say so in the report rather than raising and showing nothing.
            try:
                save_state(state)
            except OSError as e:
                summary.errors.append(
                    f"state file could not be saved ({e}) — webhook and "
                    "reaction-role bindings were NOT recorded; re-run /apply once "
                    "the data directory is writable"
                )

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

    @group.command(name="export", description="Exporter l'état actuel du serveur en YAML")
    @app_commands.describe(output="Nom du fichier à attacher (défaut: server-spec-export.yaml)")
    @admin_only()
    async def export_cmd(
        self,
        interaction: discord.Interaction,
        output: str = "server-spec-export.yaml",
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return
        yaml_str = export_guild(guild)
        import io
        f = discord.File(io.BytesIO(yaml_str.encode("utf-8")), filename=output)
        await interaction.followup.send("📤 Export prêt.", file=f, ephemeral=True)

    @webhooks_group.command(name="reveal", description="Re-DM l'URL d'un webhook existant (par id YAML)")
    @app_commands.describe(id="Identifiant YAML du webhook (ex: wh_questions_live)")
    @admin_only()
    async def webhooks_reveal(self, interaction: discord.Interaction, id: str):
        await interaction.response.defer(ephemeral=True)
        state = load_state()
        entry = state.webhooks.get(id)
        if entry is None:
            await interaction.followup.send(f"❌ Aucun webhook connu pour id `{id}`.", ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Commande à utiliser dans un serveur.", ephemeral=True)
            return
        channel = guild.get_channel(entry.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(f"❌ Salon introuvable (id={entry.channel_id}).", ephemeral=True)
            return
        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            await interaction.followup.send("❌ Manque la permission `Manage Webhooks`.", ephemeral=True)
            return
        wh = next((w for w in webhooks if w.id == entry.discord_webhook_id), None)
        if wh is None:
            await interaction.followup.send("❌ Webhook supprimé côté Discord. Re-run /apply.", ephemeral=True)
            return
        try:
            dm = await interaction.user.create_dm()
            await dm.send(f"🔐 Webhook `{id}`\n{wh.url}")
            await interaction.followup.send("📬 URL envoyée en DM.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ DM impossible (DMs fermés). Ouvre tes DMs et réessaie.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))
