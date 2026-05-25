"""Slash commands for declarative server configuration."""

from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from pydantic import ValidationError

from ..server_config.loader import load_spec


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


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfigCog(bot))
