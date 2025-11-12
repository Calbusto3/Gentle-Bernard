from __future__ import annotations

from typing import Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .config import config


def _has_role_id(member: discord.Member, role_id: Optional[int]) -> bool:
    if role_id is None:
        return False
    return any(r.id == role_id for r in member.roles)


def is_admin_member(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return _has_role_id(member, config.admin_role_id)


def is_staff_member(member: discord.Member) -> bool:
    if is_admin_member(member):
        return True
    return _has_role_id(member, config.staff_role_id)


# Prefix commands checks

def is_staff() -> Callable[[commands.Context], bool]:
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return False
        return is_staff_member(ctx.author)

    return commands.check(predicate)


def is_admin() -> Callable[[commands.Context], bool]:
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return False
        return is_admin_member(ctx.author)

    return commands.check(predicate)


# Slash commands checks

def app_is_staff() -> Callable[[discord.Interaction], bool]:
    def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member):
            return False
        return is_staff_member(inter.user)

    return app_commands.check(predicate)


def app_is_admin() -> Callable[[discord.Interaction], bool]:
    def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member):
            return False
        return is_admin_member(inter.user)

    return app_commands.check(predicate)
