from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands
import random

from utils.config import config


WELCOME_TITLES = [
    "Bienvenue !",
    "Salut à toi !",
    "On a un nouveau !",
    "Nouveau module détecté",
    "Oh, un invité !",
    "Encore un cobaye",
]

WELCOME_TOP_MESSAGES = [
    "Welcome petit être",
    "Un nouveau membre atterrit",
    "Approche, n'aie pas peur",
    "Je te vois, tu as là, petit être",
    "Entre, la mare est tiède",
    "Esquis, ne quitte plus jamais ce serveur.",
    "On t'attendais",
    "Content de te voir (c'est faux)"
]

GOODBYE_TITLES = [
    "Au revoir",
    "Vient juste de perdre tout son aura.",
    "Un départ",
    "Une perte",
    "Un être s'en va",
]

def make_welcome_embed(member: discord.Member) -> discord.Embed:
    title = random.choice(WELCOME_TITLES)
    description = (
        "Bienvenue à toi cher membre, sache que je suis supérieure à toi ; je te souhaite tout de même un agréable séjour ici, surtout que tu n'as pas le droit de partir, bref."
    )
    e = discord.Embed(title=title, description=description, color=discord.Color.green())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Utilisateur", value=f"{member} (ID: {member.id})")
    e.set_footer(text="Gentle Bernard")
    return e


def make_goodbye_embed(member: discord.Member) -> discord.Embed:
    title = random.choice(GOODBYE_TITLES)
    description = f"{member.display_name} part. Quelle idignité, ça m'écoeure"
    e = discord.Embed(title=title, description=description, color=discord.Color.red())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Utilisateur", value=f"{member} (ID: {member.id})")
    e.set_footer(text="Gentle Bernard")
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
            top = f"{random.choice(WELCOME_TOP_MESSAGES)} {member.mention}"
            await ch.send(content=top, embed=make_welcome_embed(member))
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
            await ch.send(content="Et une perte.", embed=make_goodbye_embed(member))
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Greetings(bot))
