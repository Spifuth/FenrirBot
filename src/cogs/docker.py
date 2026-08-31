"""Docker management commands"""

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..utils.docker import docker_manager


class DockerCog(commands.Cog, name="Docker"):
    """Commands for Docker container management and autocomplete"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_refresh.start()
    
    async def cog_unload(self):
        self.auto_refresh.cancel()
    
    @tasks.loop(minutes=5)
    async def auto_refresh(self):
        """Auto-refresh container list every 5 minutes"""
        await docker_manager.refresh_async()

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()
        # Initial refresh on startup
        await docker_manager.refresh_async()

    # ========== Autocomplete Functions ==========
    
    async def container_autocomplete(
        self, 
        interaction: discord.Interaction, 
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for container names"""
        containers = docker_manager.get_container_names(include_stopped=True)
        
        # Filter by current input
        if current:
            containers = [c for c in containers if current.lower() in c.lower()]
        
        # Discord limits to 25 choices
        return [
            app_commands.Choice(name=name, value=name) 
            for name in containers[:25]
        ]
    
    async def stack_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for Docker Compose stack names"""
        stacks = docker_manager.get_stacks()
        
        if current:
            stacks = [s for s in stacks if current.lower() in s.lower()]
        
        return [
            app_commands.Choice(name=name, value=name)
            for name in stacks[:25]
        ]

    # ========== Commands ==========
    
    @app_commands.command(name="containers", description="🐳 Lister tous les containers Docker")
    async def containers_slash(self, interaction: discord.Interaction):
        """List all Docker containers"""
        containers = docker_manager.get_containers()
        
        if not containers:
            await interaction.response.send_message(
                "❌ Aucun container trouvé ou Docker indisponible", 
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Containers Docker",
            color=0x2C2F33,
        )

        running = [c for c in containers if c.state == "running"]
        stopped = [c for c in containers if c.state != "running"]

        if running:
            running_lines = [c.display_name for c in running[:15]]
            if len(running) > 15:
                running_lines.append(f"+{len(running) - 15} autres")
            embed.add_field(name=f"En cours ({len(running)})", value="```\n" + "\n".join(running_lines) + "\n```", inline=True)

        if stopped:
            stopped_lines = [c.display_name for c in stopped[:15]]
            if len(stopped) > 15:
                stopped_lines.append(f"+{len(stopped) - 15} autres")
            embed.add_field(name=f"Arrêtés ({len(stopped)})", value="```\n" + "\n".join(stopped_lines) + "\n```", inline=True)

        footer = "Fenrir · Docker"
        if docker_manager.cache:
            footer += f" · {docker_manager.cache.last_updated}"
        embed.set_footer(text=footer)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="stacks", description="📦 Lister tous les stacks Docker Compose")
    async def stacks_slash(self, interaction: discord.Interaction):
        """List all Docker Compose stacks"""
        stacks = docker_manager.get_stacks()
        
        if not stacks:
            await interaction.response.send_message(
                "❌ Aucun stack trouvé ou Docker indisponible",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="Stacks Docker Compose",
            description="```\n" + "\n".join(stacks) + "\n```",
            color=0x2C2F33,
        )
        embed.set_footer(text="Fenrir · Docker")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="refresh", description="🔄 Rafraîchir la liste des containers")
    async def refresh_slash(self, interaction: discord.Interaction):
        """Manually refresh the container list"""
        await interaction.response.defer(ephemeral=True)
        
        containers = await docker_manager.refresh_async()
        stacks = docker_manager.get_stacks()
        
        await interaction.followup.send(
            f"✅ Rafraîchi ! **{len(containers)}** containers et **{len(stacks)}** stacks trouvés",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Load the cog"""
    await bot.add_cog(DockerCog(bot))
