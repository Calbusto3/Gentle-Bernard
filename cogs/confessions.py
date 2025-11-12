from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import time

from utils.config import config
from utils.db import ensure_db, next_counter, get_counter
from utils.embeds import success_embed, error_embed
from utils.permissions import app_is_staff

CONFESS_BTN_REPLY_ID = "confess:reply"
CONFESS_BTN_REPORT_ID = "confess:report"
CONFESS_BTN_DELETE_ID = "confess:delete"


@dataclass
class Confession:
    id: int
    author_id: int
    guild_id: int
    channel_id: int
    message_id: int
    thread_id: Optional[int]
    parent_id: Optional[int]
    content: str
    deleted: int


class ReplyModal(discord.ui.Modal, title="Répondre à la confession"):
    def __init__(self, parent_message_id: int):
        super().__init__(timeout=300)
        self.parent_message_id = parent_message_id
        self.content = discord.ui.TextInput(label="Votre confession", style=discord.TextStyle.paragraph, max_length=2000)
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await Confessions.handle_reply_submit(interaction, self.parent_message_id, str(self.content.value))


class ReportModal(discord.ui.Modal, title="Signaler la confession"):
    def __init__(self, target_message_id: int):
        super().__init__(timeout=300)
        self.target_message_id = target_message_id
        self.reason = discord.ui.TextInput(label="Raison du signalement", style=discord.TextStyle.paragraph, max_length=1000)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await Confessions.handle_report_submit(interaction, self.target_message_id, str(self.reason.value))


class EditOrDeleteModal(discord.ui.Modal, title="Modifier ou supprimer"):
    def __init__(self, target_message_id: int):
        super().__init__(timeout=300)
        self.target_message_id = target_message_id
        self.delete_reason = discord.ui.TextInput(label="Raison de suppression si tu confirmes que tu veux supprimer", required=False, max_length=300)
        self.new_content = discord.ui.TextInput(label="Ou alors tu veux juste la modifier, entre le nouveau contenu ici.", required=False, style=discord.TextStyle.paragraph, max_length=2000)
        self.add_item(self.delete_reason)
        self.add_item(self.new_content)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await Confessions.handle_edit_or_delete_submit(
            interaction,
            self.target_message_id,
            str(self.delete_reason.value or "").strip(),
            str(self.new_content.value or "").strip(),
        )


class ConfessionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Répondre", style=discord.ButtonStyle.primary, custom_id=CONFESS_BTN_REPLY_ID)
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        msg = interaction.message
        if not msg or not interaction.guild:
            await interaction.response.send_message("Interaction invalide.", ephemeral=True)
            return
        # Récupérer auteur de la confession pour empêcher l'auto-réponse via bouton
        conf = await Confessions.get_confession_by_message(msg.id)
        if not conf:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        if conf.author_id == interaction.user.id:
            await interaction.response.send_message("Vous ne pouvez pas répondre à votre propre confession.", ephemeral=True)
            return
        # Si déjà en thread, on poste directement; sinon on ouvre un modal pour créer thread + répondre
        if isinstance(msg.channel, discord.Thread):
            await interaction.response.send_modal(ReplyModal(msg.id))
        else:
            # même modal, on gèrera la création de thread côté traitement
            await interaction.response.send_modal(ReplyModal(msg.id))

    @discord.ui.button(label="Signaler", style=discord.ButtonStyle.secondary, custom_id=CONFESS_BTN_REPORT_ID)
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        msg = interaction.message
        if not msg:
            await interaction.response.send_message("Interaction invalide.", ephemeral=True)
            return
        conf = await Confessions.get_confession_by_message(msg.id)
        if not conf:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        if conf.author_id == interaction.user.id:
            await interaction.response.send_message("Vous ne pouvez pas signaler votre propre confession.", ephemeral=True)
            return
        await interaction.response.send_modal(ReportModal(msg.id))

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, custom_id=CONFESS_BTN_DELETE_ID)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        msg = interaction.message
        if not msg:
            await interaction.response.send_message("Interaction invalide.", ephemeral=True)
            return
        conf = await Confessions.get_confession_by_message(msg.id)
        if not conf:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        if conf.author_id != interaction.user.id:
            await interaction.response.send_message("Seul l'auteur peut utiliser ce bouton.", ephemeral=True)
            return
        await interaction.response.send_modal(EditOrDeleteModal(msg.id))


def confession_embed(title: str, content: str) -> discord.Embed:
    e = discord.Embed(title=title, description=content, color=discord.Color.green())
    e.set_footer(text="Gentle Bernard")
    return e


class Confessions(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cooldown: dict[str, float] = {}

    async def cog_load(self) -> None:
        # Enregistrer la vue persistante au démarrage
        self.bot.add_view(ConfessionView())

    def _check_cooldown(self, user_id: int, action: str, seconds: int = 30) -> bool:
        key = f"{action}:{user_id}"
        now = time.time()
        last = self._cooldown.get(key, 0)
        if now - last < seconds:
            return False
        self._cooldown[key] = now
        return True

    @staticmethod
    async def is_banned(guild_id: int, user_id: int) -> bool:
        conn = await ensure_db()
        async with conn.execute(
            "SELECT 1 FROM confession_bans WHERE user_id=? AND guild_id=? AND active=1",
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()
        await conn.close()
        return bool(row)

    @staticmethod
    async def get_confession_by_message(message_id: int) -> Optional[Confession]:
        conn = await ensure_db()
        async with conn.execute(
            "SELECT id, author_id, guild_id, channel_id, message_id, thread_id, parent_id, content, deleted FROM confessions WHERE message_id=?",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()
        await conn.close()
        if not row:
            return None
        return Confession(*row)

    @staticmethod
    async def log_to_channel(guild: discord.Guild, embed: discord.Embed) -> None:
        log_id = config.confession_logs_id
        if not log_id:
            return
        ch = guild.get_channel(log_id)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=embed)
            except Exception:
                pass

    # ---------------- Slash: confesser ----------------
    @app_commands.command(name="confesser", description="Envoyer une confession anonyme")
    async def confesser(self, interaction: discord.Interaction) -> None:
        # Modal de saisie
        class ConfessModal(discord.ui.Modal, title="Votre confession"):
            content = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=2000)

            async def on_submit(self, inner_inter: discord.Interaction) -> None:  # type: ignore[override]
                await Confessions.handle_confess_submit(inner_inter, str(self.content.value))

        await interaction.response.send_modal(ConfessModal())

    @staticmethod
    async def handle_confess_submit(interaction: discord.Interaction, content: str) -> None:
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("Commande indisponible ici.", ephemeral=True)
            return
        if await Confessions.is_banned(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("Vous êtes banni du système de confessions.", ephemeral=True)
            return
        # Cooldown anti-spam
        cog: Optional[Confessions] = interaction.client.get_cog("Confessions")  # type: ignore[attr-defined]
        if isinstance(cog, Confessions) and not cog._check_cooldown(interaction.user.id, "confess", 20):
            await interaction.response.send_message("Veuillez patienter quelques secondes avant de réessayer.", ephemeral=True)
            return
        conn = await ensure_db()
        conf_no = await next_counter(conn, f"confessions:{interaction.guild.id}")
        await conn.close()
        title = f"Confession #{conf_no}"
        embed = confession_embed(title, content)
        view = ConfessionView()
        try:
            msg = await interaction.channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message("Permissions insuffisantes pour publier.", ephemeral=True)
            return
        # Persister
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO confessions(id, author_id, guild_id, channel_id, message_id, thread_id, parent_id, content, deleted) VALUES(?,?,?,?,?,?,?,?,0)",
            (conf_no, interaction.user.id, interaction.guild.id, interaction.channel.id, msg.id, None, None, content),
        )
        await conn.commit()
        total = await get_counter(conn, f"user_conf_total:{interaction.guild.id}:{interaction.user.id}")
        # incrémenter total perso
        await conn.execute(
            "INSERT INTO counters(name, value) VALUES(?, 1) ON CONFLICT(name) DO UPDATE SET value=value+1",
            (f"user_conf_total:{interaction.guild.id}:{interaction.user.id}",),
        )
        await conn.commit()
        await conn.close()
        # DM auteur
        try:
            await interaction.user.send(
                f"Votre confession #{conf_no} a été envoyée !\nVous avez désormais {total + 1} confession(s) au total."
            )
        except Exception:
            pass
        # Log enrichi
        log = discord.Embed(title=title, description=content, color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        log.add_field(name="Auteur", value=f"<@{interaction.user.id}> ({interaction.user}) | ID: {interaction.user.id}")
        log.add_field(name="Salon", value=f"<#{interaction.channel.id}>", inline=True)
        log.add_field(name="Lien", value=f"{msg.jump_url}", inline=False)
        await Confessions.log_to_channel(interaction.guild, log)
        await interaction.response.send_message("Confession envoyée.", ephemeral=True)

    # ------------- Replies -------------
    @staticmethod
    async def handle_reply_submit(interaction: discord.Interaction, parent_message_id: int, content: str) -> None:
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("Contexte invalide.", ephemeral=True)
            return
        # Récupérer confession par message parent
        parent = await Confessions.get_confession_by_message(parent_message_id)
        if not parent:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        if await Confessions.is_banned(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message("Vous êtes banni du système de confessions.", ephemeral=True)
            return
        # Cooldown
        cog: Optional[Confessions] = interaction.client.get_cog("Confessions")  # type: ignore[attr-defined]
        if isinstance(cog, Confessions) and not cog._check_cooldown(interaction.user.id, "reply", 15):
            await interaction.response.send_message("Trop rapide, réessayez dans un instant.", ephemeral=True)
            return
        # Numéro pour la réponse
        conn = await ensure_db()
        conf_no = await next_counter(conn, f"confessions:{interaction.guild.id}")
        await conn.close()
        title = f"Confession #{conf_no} — réponse à → #{parent.id}"
        embed = confession_embed(title, content)
        # Thread
        channel = interaction.channel
        parent_msg = interaction.message
        if parent_msg is None:
            # essayer de fetch
            try:
                parent_msg = await channel.fetch_message(parent_message_id)  # type: ignore[arg-type]
            except Exception:
                parent_msg = None
        thread = None
        if parent_msg:
            if isinstance(parent_msg.channel, discord.Thread):
                thread = parent_msg.channel
            else:
                # créer thread si absent
                try:
                    thread = await parent_msg.create_thread(name=f"Confession #{parent.id}")
                except Exception:
                    thread = None
        target_channel: discord.abc.MessageableChannel = thread or channel
        try:
            msg = await target_channel.send(embed=embed, view=ConfessionView())
        except Exception:
            await interaction.response.send_message("Impossible d'envoyer la réponse.", ephemeral=True)
            return
        # Persister
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO confessions(id, author_id, guild_id, channel_id, message_id, thread_id, parent_id, content, deleted) VALUES(?,?,?,?,?,?,?,?,0)",
            (conf_no, interaction.user.id, interaction.guild.id, msg.channel.id, msg.id, thread.id if thread else None, parent.id, content),
        )
        await conn.commit()
        # DM au propriétaire de la confession initiale
        try:
            user = interaction.guild.get_member(parent.author_id)
            if user:
                await user.send(f"Vous avez reçu une réponse à votre confession #{parent.id}: {msg.jump_url}")
        except Exception:
            pass
        # Log enrichi
        log = discord.Embed(title=title, description=content, color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        log.add_field(name="Répondant", value=f"<@{interaction.user.id}> ({interaction.user}) | ID: {interaction.user.id}")
        log.add_field(name="Salon", value=f"<#{msg.channel.id}>", inline=True)
        log.add_field(name="Lien", value=f"{msg.jump_url}", inline=False)
        await Confessions.log_to_channel(interaction.guild, log)
        await interaction.response.send_message("Réponse envoyée.", ephemeral=True)

    # ------------- Reports -------------
    @staticmethod
    async def handle_report_submit(interaction: discord.Interaction, message_id: int, reason: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Contexte invalide.", ephemeral=True)
            return
        conf = await Confessions.get_confession_by_message(message_id)
        if not conf:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        # Cooldown léger
        cog: Optional[Confessions] = interaction.client.get_cog("Confessions")  # type: ignore[attr-defined]
        if isinstance(cog, Confessions) and not cog._check_cooldown(interaction.user.id, "report", 20):
            await interaction.response.send_message("Merci d'attendre un peu avant un nouveau signalement.", ephemeral=True)
            return
        e = discord.Embed(title=f"Signalement Confession #{conf.id}", color=discord.Color.red())
        e.add_field(name="Signalé par", value=f"<@{interaction.user.id}> ({interaction.user})")
        e.add_field(name="Auteur", value=f"<@{conf.author_id}>")
        e.add_field(name="Raison", value=reason or "(aucune)", inline=False)
        e.add_field(name="Salon", value=f"<#{conf.channel_id}>")
        e.add_field(name="Lien", value=f"https://discord.com/channels/{conf.guild_id}/{conf.channel_id}/{conf.message_id}", inline=False)
        await Confessions.log_to_channel(interaction.guild, e)
        await interaction.response.send_message("Signalement transmis au staff.", ephemeral=True)

    # ------------- Edit/Delete -------------
    @staticmethod
    async def handle_edit_or_delete_submit(interaction: discord.Interaction, message_id: int, delete_reason: str, new_content: str) -> None:
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("Contexte invalide.", ephemeral=True)
            return
        conf = await Confessions.get_confession_by_message(message_id)
        if not conf:
            await interaction.response.send_message("Confession introuvable.", ephemeral=True)
            return
        if conf.author_id != interaction.user.id:
            await interaction.response.send_message("Seul l'auteur peut supprimer.", ephemeral=True)
            return
        # Autoriser la suppression sans raison. Erreur seulement si les deux champs sont fournis.
        if delete_reason and new_content:
            await interaction.response.send_message("Indiquez soit une raison de suppression, soit un nouveau contenu (pas les deux).", ephemeral=True)
            return
        # Récupérer le message
        try:
            # Supporter les threads: get_channel_or_thread retourne aussi les threads
            channel = interaction.guild.get_channel_or_thread(conf.channel_id)
            msg: Optional[discord.Message] = None
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                msg = await channel.fetch_message(conf.message_id)
        except Exception:
            msg = None
        if new_content:
            # Modifier le contenu
            embed = confession_embed(f"Confession #{conf.id}", new_content)
            if msg:
                try:
                    await msg.edit(embed=embed, view=ConfessionView())
                except Exception:
                    pass
            # Log
            e = discord.Embed(title=f"Confession #{conf.id} modifiée", color=discord.Color.yellow())
            e.add_field(name="Auteur", value=f"<@{conf.author_id}>")
            e.add_field(name="Ancien contenu", value=conf.content[:1000] or "(vide)", inline=False)
            e.add_field(name="Nouveau contenu", value=new_content[:1000] or "(vide)", inline=False)
            await Confessions.log_to_channel(interaction.guild, e)
            # Persist
            conn = await ensure_db()
            await conn.execute("UPDATE confessions SET content=? WHERE id=?", (new_content, conf.id))
            await conn.commit()
            await conn.close()
            await interaction.response.send_message("Confession modifiée.", ephemeral=True)
        else:
            # Suppression
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
            e = discord.Embed(title=f"Confession #{conf.id} supprimée", color=discord.Color.dark_red())
            e.add_field(name="Auteur", value=f"<@{conf.author_id}>")
            e.add_field(name="Raison", value=delete_reason or "(aucune)")
            e.add_field(name="Contenu initial", value=conf.content[:1000] or "(vide)", inline=False)
            await Confessions.log_to_channel(interaction.guild, e)
            conn = await ensure_db()
            await conn.execute("UPDATE confessions SET deleted=1 WHERE id=?", (conf.id,))
            await conn.commit()
            await conn.close()
            try:
                user = interaction.guild.get_member(conf.author_id)
                if user:
                    await user.send(f"Votre confession #{conf.id} a bien été supprimée.")
            except Exception:
                pass
            await interaction.response.send_message("Confession supprimée.", ephemeral=True)

    # ------------- Ban/Unban confession -------------
    @app_commands.command(name="banconfession", description="Empêcher un membre d'utiliser les confessions")
    @app_is_staff()
    @app_commands.describe(membre="Membre", raison="Raison")
    async def ban_confession(self, interaction: discord.Interaction, membre: discord.Member, raison: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        conn = await ensure_db()
        await conn.execute(
            "INSERT OR REPLACE INTO confession_bans(user_id, guild_id, reason, moderator_id, active) VALUES(?,?,?,?,1)",
            (membre.id, interaction.guild.id, raison, interaction.user.id),
        )
        await conn.commit()
        await conn.close()
        try:
            await membre.send(f"Vous avez été banni du système de confessions sur {interaction.guild.name}. Raison: {raison or 'Aucune'}")
        except Exception:
            pass
        await interaction.followup.send(embed=success_embed("Banni des confessions", f"{membre.mention}"))

    @app_commands.command(name="unbanconfession", description="Autoriser de nouveau l'usage des confessions")
    @app_is_staff()
    @app_commands.describe(membre="Membre")
    async def unban_confession(self, interaction: discord.Interaction, membre: discord.Member):
        await interaction.response.defer(ephemeral=True)
        conn = await ensure_db()
        await conn.execute(
            "UPDATE confession_bans SET active=0 WHERE user_id=? AND guild_id=?",
            (membre.id, interaction.guild.id),
        )
        await conn.commit()
        await conn.close()
        try:
            await membre.send(f"Votre accès au système de confessions a été rétabli sur {interaction.guild.name}.")
        except Exception:
            pass
        await interaction.followup.send(embed=success_embed("Débanni des confessions", f"{membre.mention}"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Confessions(bot))
