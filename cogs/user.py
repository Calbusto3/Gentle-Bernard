from __future__ import annotations

from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import success_embed, error_embed


class UserInfo(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    user = app_commands.Group(name="user", description="Commandes utilisateur")

    async def _member_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        if not interaction.guild:
            return []
        current_lower = current.lower()
        choices: List[app_commands.Choice[str]] = []
        # Try ID exact
        if current.isdigit():
            m = interaction.guild.get_member(int(current))
            if m:
                choices.append(app_commands.Choice(name=f"{m} ({m.id})", value=str(m.id)))
        # Search by display_name or name
        for m in interaction.guild.members[:200]:  # soft cap for performance
            name_hits = [m.display_name.lower(), m.name.lower()]
            if current_lower and not any(current_lower in x for x in name_hits):
                continue
            choices.append(app_commands.Choice(name=f"{m.display_name} ({m})", value=str(m.id)))
            if len(choices) >= 20:
                break
        return choices

    def _resolve_member(self, guild: discord.Guild, token: Optional[str], fallback: Optional[discord.Member]) -> Optional[discord.Member]:
        if token is None or token.strip() == "":
            return fallback
        t = token.strip()
        # mention
        if t.startswith("<@") and t.endswith(">"):
            t = t.replace("<@!", "").replace("<@", "").replace(">", "")
        if t.isdigit():
            m = guild.get_member(int(t))
            if m:
                return m
        # name or display name
        return discord.utils.find(lambda u: u.name == t or (u.nick and u.nick == t) or u.display_name == t, guild.members)

    @user.command(name="info", description="Informations sur un utilisateur")
    @app_commands.describe(cible="ID / mention / nom / surnom (facultatif)")
    @app_commands.autocomplete(cible=_member_autocomplete)
    async def user_info(self, interaction: discord.Interaction, cible: Optional[str] = None):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("Commande en DM non supportée"), ephemeral=True)
            return
        me = interaction.user if isinstance(interaction.user, discord.Member) else None
        target = self._resolve_member(interaction.guild, cible, me)
        if target is None:
            await interaction.response.send_message(embed=error_embed("Utilisateur introuvable"), ephemeral=True)
            return

        color = target.top_role.color if getattr(target.top_role, "color", None) and target.top_role.color.value else discord.Color.blurple()
        e = discord.Embed(title=f"Infos de {target.display_name}", color=color)
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="Mention", value=target.mention)
        e.add_field(name="ID", value=str(target.id))
        e.add_field(name="Nom", value=str(target))
        e.add_field(name="Surnom", value=target.nick or "(aucun)")
        e.add_field(name="Créé le", value=discord.utils.format_dt(target.created_at, style='F'), inline=False)
        if target.joined_at:
            e.add_field(name="A rejoint le", value=discord.utils.format_dt(target.joined_at, style='F'), inline=False)
        role_list = [r.mention for r in target.roles if r.name != '@everyone']
        e.add_field(name="Rôles", value=", ".join(role_list)[:1000] or "(aucun)", inline=False)
        e.add_field(name="Plus haut rôle", value=target.top_role.mention if target.top_role else "(aucun)")
        e.add_field(name="Bot?", value="Oui" if target.bot else "Non")
        try:
            if target.activity:
                e.add_field(name="Activité", value=str(target.activity), inline=False)
            if target.status:
                e.add_field(name="Statut", value=str(target.status))
        except Exception:
            pass

        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UserInfo(bot))
