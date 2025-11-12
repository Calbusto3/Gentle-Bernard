from __future__ import annotations

import time
import discord
from discord import app_commands
from discord.ext import commands
from utils.permissions import is_staff, app_is_staff
from utils.config import config


class Basic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Ensure tree is synced once when bot is ready
        if not getattr(self.bot, "_basic_synced", False):
            try:
                await self.bot.tree.sync()
            except Exception:
                pass
            finally:
                self.bot._basic_synced = True

    # Prefix command: ping
    @commands.command(name="ping", help="Affiche la latence du bot")
    @is_staff()
    async def ping(self, ctx: commands.Context) -> None:
        start = time.perf_counter()
        message = await ctx.send("Pinging...")
        end = time.perf_counter()
        api_latency_ms = self.bot.latency * 1000
        roundtrip_ms = (end - start) * 1000
        await message.edit(content=f"Pong! WebSocket: {api_latency_ms:.1f} ms | RTT: {roundtrip_ms:.1f} ms. Je vie.. ou presque")

    # Prefix command: health
    @commands.command(name="health", help="Vérifie l'état du bot")
    @is_staff()
    async def health(self, ctx: commands.Context) -> None:
        embed = discord.Embed(title="Statut du bot", color=discord.Color.green())
        embed.add_field(name="Connecté en tant que", value=f"{self.bot.user} ({self.bot.user.id})", inline=False)
        embed.add_field(name="Guildes", value=str(len(self.bot.guilds)))
        embed.set_footer(text="Gentle Bernard")
        await ctx.send(embed=embed)



    # Slash command: /ping
    @app_commands.command(name="ping", description="Affiche la latence du bot (staff)")
    @app_is_staff()
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        start = time.perf_counter()
        await interaction.response.defer(thinking=True)
        end = time.perf_counter()
        api_latency_ms = self.bot.latency * 1000
        roundtrip_ms = (end - start) * 1000
        await interaction.followup.send(f"Pong! WebSocket: {api_latency_ms:.1f} ms | RTT: {roundtrip_ms:.1f} ms")

    # Error handling for prefix commands
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("⛔ Vous n'avez pas la permission d'exécuter cette commande.")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ Argument manquant: `{error.param.name}`")
            return
        await ctx.send("❌ Une erreur est survenue. Réessayez plus tard.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Basic(bot))
