from __future__ import annotations

import discord


def success_embed(title: str, description: str | None = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description or discord.Embed.Empty, color=discord.Color.green())
    return e


def error_embed(title: str, description: str | None = None) -> discord.Embed:
    e = discord.Embed(title=title, description=description or discord.Embed.Empty, color=discord.Color.red())
    return e


essential_red = discord.Color.red

essential_green = discord.Color.green
