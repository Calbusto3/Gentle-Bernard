from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands
import random

from utils.config import config
from utils.permissions import is_admin
from utils.db import ensure_db


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

    async def _get_settings(self, guild_id: int) -> tuple[bool, Optional[int], Optional[int]]:
        conn = await ensure_db()
        async with conn.execute(
            "SELECT enabled, welcome_channel_id, goodbye_channel_id FROM welcome_settings WHERE guild_id=?",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
        await conn.close()
        if not row:
            # Default: enabled, fallback to config
            return True, getattr(config, "welcome_channel_id", None), getattr(config, "goodbye_channel_id", None)
        enabled, w, g = row
        return bool(enabled), int(w) if w else getattr(config, "welcome_channel_id", None), int(g) if g else getattr(config, "goodbye_channel_id", None)

    def _get_channel(self, guild: discord.Guild, channel_id: Optional[int]) -> Optional[discord.TextChannel]:
        if not channel_id:
            return None
        ch = guild.get_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    # -------- Admin commands --------
    @commands.command(name="welcome_on", help="Activer les messages d'arrivée et de départ (admin)")
    @is_admin()
    async def welcome_on(self, ctx: commands.Context):
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO welcome_settings(guild_id, enabled, welcome_channel_id, goodbye_channel_id) VALUES(?,?,NULL,NULL) ON CONFLICT(guild_id) DO UPDATE SET enabled=1, updated_at=CURRENT_TIMESTAMP",
            (ctx.guild.id, 1),  # type: ignore[union-attr]
        )
        await conn.commit()
        await conn.close()
        await ctx.send("Système de bienvenue activé.")

    @commands.command(name="welcome_off", help="Désactiver les messages d'arrivée et de départ (admin)")
    @is_admin()
    async def welcome_off(self, ctx: commands.Context):
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO welcome_settings(guild_id, enabled, welcome_channel_id, goodbye_channel_id) VALUES(?,?,NULL,NULL) ON CONFLICT(guild_id) DO UPDATE SET enabled=0, updated_at=CURRENT_TIMESTAMP",
            (ctx.guild.id, 0),  # type: ignore[union-attr]
        )
        await conn.commit()
        await conn.close()
        await ctx.send("Système de bienvenue désactivé.")

    @commands.command(name="welcome_arrive_set", help="Définir le salon d'arrivée (admin)")
    @is_admin()
    async def welcome_arrive_set(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or (ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None)
        if not channel:
            await ctx.send("Spécifiez un salon texte.")
            return
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO welcome_settings(guild_id, enabled, welcome_channel_id, goodbye_channel_id) VALUES(?,1,?,NULL) ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=excluded.welcome_channel_id, updated_at=CURRENT_TIMESTAMP",
            (ctx.guild.id, channel.id),  # type: ignore[union-attr]
        )
        await conn.commit()
        await conn.close()
        await ctx.send(f"Salon d'arrivée défini sur {channel.mention}.")

    @commands.command(name="welcome_depart_set", help="Définir le salon de départ (admin)")
    @is_admin()
    async def welcome_depart_set(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or (ctx.channel if isinstance(ctx.channel, discord.TextChannel) else None)
        if not channel:
            await ctx.send("Spécifiez un salon texte.")
            return
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO welcome_settings(guild_id, enabled, welcome_channel_id, goodbye_channel_id) VALUES(?,1,NULL,?) ON CONFLICT(guild_id) DO UPDATE SET goodbye_channel_id=excluded.goodbye_channel_id, updated_at=CURRENT_TIMESTAMP",
            (ctx.guild.id, channel.id),  # type: ignore[union-attr]
        )
        await conn.commit()
        await conn.close()
        await ctx.send(f"Salon de départ défini sur {channel.mention}.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild:
            return
        enabled, w_id, _ = await self._get_settings(member.guild.id)
        if not enabled:
            return
        ch = self._get_channel(member.guild, w_id)
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
        enabled, _, g_id = await self._get_settings(member.guild.id)
        if not enabled:
            return
        ch = self._get_channel(member.guild, g_id)
        if not ch:
            return
        try:
            await ch.send(content="Et une perte.", embed=make_goodbye_embed(member))
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Greetings(bot))
