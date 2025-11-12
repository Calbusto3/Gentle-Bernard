from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from utils.config import config


def make_welcome_embed(member: discord.Member) -> discord.Embed:
    e = discord.Embed(
        title="Bienvenue !",
        description=f"{member.mention} a rejoint le serveur.",
        color=discord.Color.green(),
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Utilisateur", value=f"{member} (ID: {member.id})")
    return e


def make_goodbye_embed(member: discord.Member) -> discord.Embed:
    e = discord.Embed(
        title="Au revoir",
        description=f"{member.mention} a quitté le serveur.",
        color=discord.Color.red(),
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Utilisateur", value=f"{member} (ID: {member.id})")
    return e


class Greetings(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _get_channel(self, guild: discord.Guild, channel_id: Optional[int]) -> Optional[discord.TextChannel]:
        if not channel_id:
            return None
        ch = guild.get_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild:
            return
        ch = self._get_channel(member.guild, config.welcome_channel_id)
        if not ch:
            return
        try:
            await ch.send(embed=make_welcome_embed(member))
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.guild:
            return
        ch = self._get_channel(member.guild, config.goodbye_channel_id)
        if not ch:
            return
        try:
            await ch.send(embed=make_goodbye_embed(member))
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Greetings(bot))
