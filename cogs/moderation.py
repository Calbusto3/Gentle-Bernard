from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.permissions import is_staff, is_admin, app_is_staff, app_is_admin
from utils.config import config
from utils.durations import parse_duration, humanize_delta
from utils.embeds import success_embed, error_embed


def _get_staff_role(guild: discord.Guild) -> Optional[discord.Role]:
    if config.staff_role_id is None:
        return None
    return guild.get_role(config.staff_role_id)


def _get_admin_role(guild: discord.Guild) -> Optional[discord.Role]:
    if config.admin_role_id is None:
        return None
    return guild.get_role(config.admin_role_id)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---------------------- Helpers ----------------------

    def _role_position(self, member: discord.Member) -> int:
        return member.top_role.position if member.top_role else 0

    def _can_act_on(self, actor: discord.Member, target: discord.Member, guild: discord.Guild) -> tuple[bool, str | None]:
        if target == actor:
            return False, "Vous ne pouvez pas agir sur vous-même."
        if target == guild.owner:
            return False, "Impossible d'agir sur le propriétaire du serveur."
        if actor.top_role <= target.top_role and not actor.guild_permissions.administrator:
            return False, "Votre rôle est inférieur ou égal à la cible."
        me = guild.me
        if me and me.top_role <= target.top_role:
            return False, "Le rôle du bot est inférieur ou égal à la cible."
        return True, None

    # ---------------------- Channel lock/hide ----------------------

    @commands.command(name="lock", help="Verrouille le salon. Option: 'all' (admins seulement)")
    @is_staff()
    async def lock_cmd(self, ctx: commands.Context, scope: Optional[str] = None) -> None:
        channel: discord.TextChannel = ctx.channel  # type: ignore[assignment]
        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        overwrites = channel.overwrites_for(everyone)

        if scope and scope.lower() == "all":
            # admins only can use 'all'
            if not ctx.author.guild_permissions.administrator and not any(
                r.id == config.admin_role_id for r in getattr(ctx.author, "roles", [])
            ):
                await ctx.send(embed=error_embed("Accès refusé", "Seuls les administrateurs peuvent utiliser 'all' petit être."))
                return
            overwrites.send_messages = False
            await channel.set_permissions(everyone, overwrite=overwrites, reason=f"Lock all par {ctx.author}")
            await ctx.send(embed=success_embed("Salon verrouillé pour tout le monde", "Seuls les admins peuvent parler."))
            return

        # staff-only speaking: block everyone, allow staff role
        staff = _get_staff_role(ctx.guild)
        if staff is None:
            await ctx.send(embed=error_embed("Rôle staff introuvable", "Configurez STAFF_ROLE_ID dans .env (<@1033834366822002769>)"))
            return
        overwrites.send_messages = False
        await channel.set_permissions(everyone, overwrite=overwrites, reason=f"Lock staff par {ctx.author}")
        staff_ow = channel.overwrites_for(staff)
        staff_ow.send_messages = True
        await channel.set_permissions(staff, overwrite=staff_ow, reason="Autoriser staff à parler")
        await ctx.send(embed=success_embed("Salon verrouillé", "Seul le staff peut parler."))

    @commands.command(name="unlock", help="Déverrouille le salon pour tous")
    @is_staff()
    async def unlock_cmd(self, ctx: commands.Context) -> None:
        channel: discord.TextChannel = ctx.channel  # type: ignore[assignment]
        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        await channel.set_permissions(everyone, send_messages=None, reason=f"Unlock par {ctx.author}")
        staff = _get_staff_role(ctx.guild)
        if staff:
            await channel.set_permissions(staff, send_messages=None)
        await ctx.send(embed=success_embed("Salon déverrouillé", "Tout le monde peut parler, à nouveau."))

    @commands.command(name="hide", help="Cache le salon. Option: 'all' (admins seulement)")
    @is_staff()
    async def hide_cmd(self, ctx: commands.Context, scope: Optional[str] = None) -> None:
        channel: discord.TextChannel = ctx.channel  # type: ignore[assignment]
        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        overwrites = channel.overwrites_for(everyone)

        if scope and scope.lower() == "all":
            if not ctx.author.guild_permissions.administrator and not any(
                r.id == config.admin_role_id for r in getattr(ctx.author, "roles", [])
            ):
                await ctx.send(embed=error_embed("Accès refusé", "Seuls les administrateurs peuvent utiliser 'all'."))
                return
            overwrites.view_channel = False
            await channel.set_permissions(everyone, overwrite=overwrites, reason=f"Hide all par {ctx.author}")
            await ctx.send(embed=success_embed("Salon caché (all)", "Seuls les admins peuvent voir, petit être."))
            return

        staff = _get_staff_role(ctx.guild)
        if staff is None:
            await ctx.send(embed=error_embed("Rôle staff introuvable", "Configurez STAFF_ROLE_ID dans .env (<@1033834366822002769>)"))
            return
        overwrites.view_channel = False
        await channel.set_permissions(everyone, overwrite=overwrites, reason=f"Hide staff par {ctx.author}")
        staff_ow = channel.overwrites_for(staff)
        staff_ow.view_channel = True
        await channel.set_permissions(staff, overwrite=staff_ow, reason="Autoriser staff à voir")
        await ctx.send(embed=success_embed("Salon caché", "Seul le staff peut voir."))

    @commands.command(name="unhide", help="Affiche le salon pour tous")
    @is_staff()
    async def unhide_cmd(self, ctx: commands.Context) -> None:
        channel: discord.TextChannel = ctx.channel  # type: ignore[assignment]
        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        await channel.set_permissions(everyone, view_channel=None, reason=f"Unhide par {ctx.author}")
        staff = _get_staff_role(ctx.guild)
        if staff:
            await channel.set_permissions(staff, view_channel=None)
        await ctx.send(embed=success_embed("Salon affiché", "Tout le monde peut voir, à nouveau."))

    # ---------------------- Mute / Unmute ----------------------

    async def _get_last_author(self, channel: discord.TextChannel, exclude_id: int) -> Optional[discord.Member]:
        async for msg in channel.history(limit=50):
            if msg.author.id != exclude_id and isinstance(msg.author, discord.Member):
                return msg.author
        return None

    @commands.command(name="mute", help="Mute via timeout. Usage: +mute [membre?] [durée?] [raison?]")
    @is_staff()
    async def mute_cmd(self, ctx: commands.Context, *args: str) -> None:
        member: Optional[discord.Member] = None
        duration: Optional[timedelta] = None
        reason = None

        def resolve_member(token: str) -> Optional[discord.Member]:
            if not token:
                return None
            m = None
            if token.isdigit():
                m = ctx.guild.get_member(int(token))  # type: ignore[union-attr]
            if not m:
                m = discord.utils.find(lambda u: u.name == token or getattr(u, 'display_name', '') == token, ctx.guild.members)  # type: ignore[union-attr]
            return m

        if not args:
            member = await self._get_last_author(ctx.channel, ctx.author.id)  # type: ignore[arg-type]
            duration = timedelta(minutes=10)
        else:
            first = args[0]
            dur_candidate = parse_duration(first)
            if dur_candidate is not None:
                member = await self._get_last_author(ctx.channel, ctx.author.id)  # type: ignore[arg-type]
                duration = dur_candidate
                reason = " ".join(args[1:]) or None
            else:
                member = resolve_member(first) or (ctx.message.mentions[0] if ctx.message.mentions else None)
                if member is None:
                    await ctx.send(embed=error_embed("Membre introuvable", "Spécifiez un membre valide."))
                    return
                if len(args) >= 2:
                    duration = parse_duration(args[1])
                    reason = " ".join(args[2:]) or None
                else:
                    duration = timedelta(minutes=10)
                    reason = None

        if member is None:
            await ctx.send(embed=error_embed("Impossible de déterminer le membre à mute, désolé."))
            return
        if duration is None:
            duration = timedelta(minutes=10)

        ok, msg = self._can_act_on(ctx.author, member, ctx.guild)  # type: ignore[arg-type]
        if not ok:
            await ctx.send(embed=error_embed("Action refusée", msg or ""))
            return
        try:
            await member.timeout(duration, reason=reason or f"Mute par {ctx.author}")
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Permissions insuffisantes"))
            return
        except Exception as e:
            await ctx.send(embed=error_embed("Erreur mute", str(e)))
            return

        try:
            await member.send(f"Vous avez été mute sur {ctx.guild.name} pendant {humanize_delta(duration)}. Raison: {reason or 'Aucune'}")  # type: ignore[union-attr]
        except Exception:
            pass
        await ctx.send(embed=success_embed("Membre mute", f"{member.mention} pendant {humanize_delta(duration)}"))

    @commands.command(name="unmute", help="Retire le mute (timeout)")
    @is_staff()
    async def unmute_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        if member is None:
            member = await self._get_last_author(ctx.channel, ctx.author.id)  # type: ignore[arg-type]
            if member is None:
                await ctx.send(embed=error_embed("Aucun membre trouvé pour unmute, désolé."))
                return
        try:
            await member.timeout(None, reason=f"Unmute par {ctx.author}")
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Permissions insuffisantes"))
            return
        await ctx.send(embed=success_embed("Membre unmute", f"{member.mention}"))

    # Slash versions
    @app_commands.command(name="mute", description="Mute un membre (timeout)")
    @app_is_staff()
    @app_commands.describe(member="Membre", duree="Ex: 10m, 2h, 1d", raison="Raison")
    async def mute_slash(self, interaction: discord.Interaction, member: discord.Member, duree: Optional[str] = None, raison: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        td = parse_duration(duree) if duree else timedelta(minutes=10)
        try:
            await member.timeout(td, reason=raison or f"Mute par {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Permissions insuffisantes"))
            return
        try:
            await member.send(f"Vous avez été mute sur {interaction.guild.name} pendant {humanize_delta(td)}. Raison: {raison or 'Aucune'}")  # type: ignore[union-attr]
        except Exception:
            pass
        await interaction.followup.send(embed=success_embed("Membre mute", f"{member.mention} pendant {humanize_delta(td)}"))

    @app_commands.command(name="unmute", description="Retire le mute (timeout)")
    @app_is_staff()
    @app_commands.describe(member="Membre")
    async def unmute_slash(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        try:
            await member.timeout(None, reason=f"Unmute par {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Permissions insuffisantes"))
            return
        await interaction.followup.send(embed=success_embed("Membre unmute", f"{member.mention}"))

    # ---------------------- Ban / Unban / Kick ----------------------

    @commands.command(name="ban", help="Bannit un membre")
    @is_staff()
    async def ban_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None, *, reason: Optional[str] = None) -> None:
        if member is None:
            await ctx.send(embed=error_embed("Spécifiez un membre à bannir"))
            return
        ok, msg = self._can_act_on(ctx.author, member, ctx.guild)  # type: ignore[arg-type]
        if not ok:
            await ctx.send(embed=error_embed("Action refusée", msg or ""))
            return
        # Vérifier permissions bot
        if not ctx.guild.me.guild_permissions.ban_members:  # type: ignore[union-attr]
            await ctx.send(embed=error_embed("Permissions du bot manquantes", "Ban Members"))
            return
        try:
            await ctx.guild.ban(member, reason=reason)  # type: ignore[union-attr]
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Permissions insuffisantes"))
            return
        await ctx.send(embed=success_embed("Membre banni", f"{member} | Raison: {reason or 'Aucune'}"))

    @commands.command(name="unban", help="Débannit un utilisateur par ID ou nom#discrim")
    @is_staff()
    async def unban_cmd(self, ctx: commands.Context, *, user: str) -> None:
        bans = await ctx.guild.bans()  # type: ignore[union-attr]
        target = None
        if user.isdigit():
            uid = int(user)
            for e in bans:
                if e.user.id == uid:
                    target = e.user
                    break
        if target is None:
            for e in bans:
                if str(e.user) == user or e.user.name == user:
                    target = e.user
                    break
        if target is None:
            await ctx.send(embed=error_embed("Utilisateur non trouvé dans la liste des bannis"))
            return
        await ctx.guild.unban(target, reason=f"Unban par {ctx.author}")  # type: ignore[union-attr]
        await ctx.send(embed=success_embed("Utilisateur débanni", f"{target}"))

    @commands.command(name="kick", help="Expulse un membre")
    @is_staff()
    async def kick_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None, *, reason: Optional[str] = None) -> None:
        if member is None:
            await ctx.send(embed=error_embed("Spécifiez un membre à expulser"))
            return
        ok, msg = self._can_act_on(ctx.author, member, ctx.guild)  # type: ignore[arg-type]
        if not ok:
            await ctx.send(embed=error_embed("Action refusée", msg or ""))
            return
        if not ctx.guild.me.guild_permissions.kick_members:  # type: ignore[union-attr]
            await ctx.send(embed=error_embed("Permissions du bot manquantes", "Kick Members"))
            return
        try:
            await ctx.guild.kick(member, reason=reason)  # type: ignore[union-attr]
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Permissions insuffisantes"))
            return
        await ctx.send(embed=success_embed("Membre expulsé", f"{member} | Raison: {reason or 'Aucune'}"))

    # Slash variants
    @app_commands.command(name="ban", description="Bannit un membre")
    @app_is_staff()
    @app_commands.describe(member="Membre", raison="Raison")
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, raison: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        ok, msg = self._can_act_on(interaction.user, member, interaction.guild)  # type: ignore[arg-type]
        if not ok:
            await interaction.followup.send(embed=error_embed("Action refusée", msg or ""))
            return
        try:
            await interaction.guild.ban(member, reason=raison)  # type: ignore[union-attr]
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Permissions insuffisantes"))
            return
        await interaction.followup.send(embed=success_embed("Membre banni", f"{member}"))

    @app_commands.command(name="unban", description="Débannit un utilisateur (ID ou nom)")
    @app_is_staff()
    @app_commands.describe(utilisateur="ID ou nom")
    async def unban_slash(self, interaction: discord.Interaction, utilisateur: str):
        await interaction.response.defer(ephemeral=True)
        bans = await interaction.guild.bans()  # type: ignore[union-attr]
        target = None
        if utilisateur.isdigit():
            uid = int(utilisateur)
            for e in bans:
                if e.user.id == uid:
                    target = e.user
                    break
        if target is None:
            for e in bans:
                if str(e.user) == utilisateur or e.user.name == utilisateur:
                    target = e.user
                    break
        if target is None:
            await interaction.followup.send(embed=error_embed("Utilisateur non trouvé dans les bannis"))
            return
        await interaction.guild.unban(target, reason=f"Unban par {interaction.user}")  # type: ignore[union-attr]
        await interaction.followup.send(embed=success_embed("Utilisateur débanni", f"{target}"))

    @app_commands.command(name="kick", description="Expulse un membre")
    @app_is_staff()
    @app_commands.describe(member="Membre", raison="Raison")
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, raison: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        ok, msg = self._can_act_on(interaction.user, member, interaction.guild)  # type: ignore[arg-type]
        if not ok:
            await interaction.followup.send(embed=error_embed("Action refusée", msg or ""))
            return
        try:
            await interaction.guild.kick(member, reason=raison)  # type: ignore[union-attr]
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("Permissions insuffisantes"))
            return
        await interaction.followup.send(embed=success_embed("Membre expulsé", f"{member}"))

    # ---------------------- Purge / Supprimer ----------------------

    @commands.command(name="supprimer", aliases=["supp"], help="Supprime un nombre de messages dans le salon (max 200)")
    @is_staff()
    async def supprimer_cmd(self, ctx: commands.Context, nombre: Optional[int] = None) -> None:
        if nombre is None or nombre <= 0:
            await ctx.send(embed=error_embed("Nombre invalide", "Spécifiez un entier positif."))
            return
        if nombre > 200:
            nombre = 200
        if not ctx.guild.me.guild_permissions.manage_messages:  # type: ignore[union-attr]
            await ctx.send(embed=error_embed("Permissions du bot manquantes", "Manage Messages"))
            return
        try:
            deleted = await ctx.channel.purge(limit=nombre + 1)  # type: ignore[arg-type]
        except discord.Forbidden:
            await ctx.send(embed=error_embed("Permissions insuffisantes"))
            return
        except Exception as e:
            await ctx.send(embed=error_embed("Erreur suppression", str(e)))
            return
        count = max(0, len(deleted) - 1)
        await ctx.send(embed=success_embed("Suppression effectuée", f"{count} message(s) supprimé(s)."), delete_after=5)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
