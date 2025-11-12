from __future__ import annotations

from typing import List, Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands
from utils.config import config

DEFAULT_COLOR = discord.Color.green()

# Définition des commandes documentées (nous n'affichons pas ping/health)
HELP_ENTRIES = [
    {
        "key": "lock",
        "label": "lock -> verrouiller le salon",
        "type": "prefix",
        "title": "lock",
        "summary": "Verrouille un salon textuel pour retirer la permission aux membres d'écrir.",
        "usage": "+lock [all]",
        "details": (
            "Sans argument: seul le staff peut parler.\n"
            "Avec 'all': seuls les administrateurs peuvent parler."
        ),
        "examples": ["+lock", "+lock all"],
        "permissions": "Staff",
    },
    {
        "key": "unlock",
        "label": "unlock -> déverrouiller le salon",
        "type": "prefix",
        "title": "unlock",
        "summary": "Déverrouiller un salon verrouillé pour redonner la permission aux membres d'écrir.",
        "usage": "+unlock",
        "details": "Rétablit les permissions de tout le monde dans le salon.",
        "examples": ["+unlock"],
        "permissions": "Staff",
    },
    {
        "key": "hide",
        "label": "hide -> cacher le salon",
        "type": "prefix",
        "title": "hide",
        "summary": "Cache un salon de sorte que plus aucun membre puisse le voir.",
        "usage": "+hide [all]",
        "details": (
            "Sans argument: seul le staff voit le salon.\n"
            "Avec 'all': seuls les administrateurs voient le salon."
        ),
        "examples": ["+hide", "+hide all"],
        "permissions": "Staff",
    },
    {
        "key": "unhide",
        "label": "unhide -> afficher le salon",
        "type": "prefix",
        "title": "unhide",
        "summary": "Rétablir la visibilité d'un salon caché.",
        "usage": "+unhide",
        "details": "Rétablit la visibilité du salon pour tout le monde.",
        "examples": ["+unhide"],
        "permissions": "Staff",
    },
    {
        "key": "mute",
        "label": "mute -> rendre muet un membre (timeout)",
        "type": "both",
        "title": "mute",
        "summary": "Muter un membre.",
        "usage": "+mute [membre?] [durée?] [raison?] | /mute membre [durée] [raison]",
        "details": (
            "Préfixe: si aucun membre n'est précisé, cible le dernier auteur du salon.\n"
            "La durée accepte: 10s, 5m, 2h, 1d, 1w (défaut 10m)."
        ),
        "examples": ["+mute", "+mute @Membre 30m spam", "/mute membre:@Membre duree:30m raison:spam"],
        "permissions": "Staff",
    },
    {
        "key": "unmute",
        "label": "unmute -> retirer le mute",
        "type": "both",
        "title": "unmute",
        "summary": "Retire le mute d'un membre.",
        "usage": "+unmute [membre?] | /unmute membre",
        "details": "Préfixe: si aucun membre n'est précisé, cible le dernier auteur du salon.",
        "examples": ["+unmute", "/unmute membre:@Membre"],
        "permissions": "Staff",
    },
    {
        "key": "ban",
        "label": "ban -> bannir un membre",
        "type": "both",
        "title": "ban",
        "summary": "Bannit un membre du serveur.",
        "usage": "+ban @Membre [raison] | /ban membre [raison]",
        "details": "Tente d'envoyer un MP avant la sanction.",
        "examples": ["+ban @Membre pub", "/ban membre:@Membre raison:pub"],
        "permissions": "Staff",
    },
    {
        "key": "unban",
        "label": "unban -> débannir un utilisateur",
        "type": "both",
        "title": "unban",
        "summary": "Débannit un utilisateur par ID ou nom.",
        "usage": "+unban <id|nom> | /unban utilisateur",
        "details": "Recherche dans la liste des bannis.",
        "examples": ["+unban 1234567890"],
        "permissions": "Staff",
    },
    {
        "key": "kick",
        "label": "kick -> expulser un membre",
        "type": "both",
        "title": "kick",
        "summary": "Expulse un membre du serveur.",
        "usage": "+kick @Membre [raison] | /kick membre [raison]",
        "details": "Tente d'envoyer un MP avant l'action.",
        "examples": ["+kick @Membre comportement"],
        "permissions": "Staff",
    },
    {
        "key": "slowmode",
        "label": "slowmode -> régler le mode lent",
        "type": "prefix",
        "title": "slowmode",
        "summary": "Règle le délai entre messages dans un salon.",
        "usage": "+slowmode|+slowmod|+sm off|10s|5m|30",
        "details": "Max 6h (21600s). Accepte secondes, 10s, 5m, etc.",
        "examples": ["+sm off", "+sm 10s", "+slowmod 120"],
        "permissions": "Staff",
    },
    {
        "key": "supprimer",
        "label": "supprimer -> supprimer des messages",
        "type": "prefix",
        "title": "supprimer",
        "summary": "Supprime un nombre de messages dans le salon.",
        "usage": "+supprimer|+supp [nombre]",
        "details": "Supprime jusqu'à 200 messages récents (incluant la commande). Nécessite Manage Messages pour le bot.",
        "examples": ["+supprimer 50", "+supp 10"],
        "permissions": "Staff",
    },
    {
        "key": "confesser",
        "label": "confesser -> envoyer une confession",
        "type": "slash",
        "title": "confesser",
        "summary": "Faire une confession anonyme.",
        "usage": "/confesser",
        "details": "Crée un message anonyme numéroté avec des boutons (répondre, signaler, supprimer). Cooldown léger et logs au staff.",
        "examples": ["/confesser"],
        "permissions": "Aucune pour confesser",
    },
    {
        "key": "banconfession",
        "label": "banconfession -> bannir des confessions",
        "type": "slash",
        "title": "banconfession",
        "summary": "Empêche un membre d'utiliser le système de confessions.",
        "usage": "/banconfession membre [raison]",
        "details": "Le membre ne peut plus envoyer ou répondre aux confessions. Envoi d'un DM et log.",
        "examples": ["/banconfession membre:@User raison:abus"],
        "permissions": "Staff",
    },
    {
        "key": "unbanconfession",
        "label": "unbanconfession -> rétablir l'accès",
        "type": "slash",
        "title": "unbanconfession",
        "summary": "Rend l'accès aux confessions à un membre banni.",
        "usage": "/unbanconfession membre",
        "details": "Envoi d'un DM et log au staff.",
        "examples": ["/unbanconfession membre:@User"],
        "permissions": "Staff",
    },
    {
        "key": "user info",
        "label": "user info -> informations sur un utilisateur",
        "type": "slash",
        "title": "user info",
        "summary": "Affiche les informations d'un utilisateur.",
        "usage": "/user info [cible]",
        "details": "Si vide, affiche vos infos. Autocomplétion disponible.",
        "examples": ["/user info", "/user info cible:@Membre"],
        "permissions": "Aucune requise pour consulter.",
    },
]

FILTERS = ("tous", "prefix", "slash")


def _filter_entries(filter_key: str) -> List[dict]:
    if filter_key == "prefix":
        return [e for e in HELP_ENTRIES if e["type"] in ("prefix", "both")]
    if filter_key == "slash":
        return [e for e in HELP_ENTRIES if e["type"] in ("slash", "both")]
    return HELP_ENTRIES


def _find_entry(key: str) -> Optional[dict]:
    low = key.lower().strip()
    for e in HELP_ENTRIES:
        if e["key"] == low or e["title"].lower() == low or e["label"].lower().startswith(low):
            return e
    return None


class HelpSelect(discord.ui.Select):
    def __init__(self, entries: List[dict]):
        options = [
            discord.SelectOption(label=e["label"], value=e["key"]) for e in entries
        ]
        super().__init__(placeholder="Sélectionnez une commande", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        entry = _find_entry(key)
        if not entry:
            await interaction.response.send_message("Entrée d'aide introuvable.", ephemeral=True)
            return
        embed = build_help_embed(entry)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, entries: List[dict]):
        super().__init__(timeout=120)
        self.add_item(HelpSelect(entries))


def build_help_embed(entry: dict) -> discord.Embed:
    e = discord.Embed(title=f"Aide: {entry['title']}", color=DEFAULT_COLOR, description=entry["summary"])
    e.add_field(name="Type", value=entry["type"].upper())
    e.add_field(name="Usage", value=f"`{entry['usage']}`", inline=False)
    e.add_field(name="Détails", value=entry["details"], inline=False)
    if entry.get("examples"):
        e.add_field(name="Exemples", value="\n".join(f"`{x}`" for x in entry["examples"]), inline=False)
    if entry.get("permissions"):
        e.add_field(name="Permissions", value=entry["permissions"], inline=False)
    e.set_footer(text="Gentle Bernard")
    return e


def build_welcome_embed(filter_key: str) -> discord.Embed:
    description = (
        "Je suis le bot officiel du serveur, créé avec soin par Calbusto (``@.calbusto/1033834366822002769``).\n"
        f"- Préfixe: `{config.prefix}`\n"
        "- Date de création: sam 11/25\n\n"
        "Sélectionnez une commande dans le menu déroulant.\n"
        f"Filtre courant: **{filter_key}**."
    )
    e = discord.Embed(title="Aide - Menu", description=description, color=DEFAULT_COLOR)
    e.set_footer(text="Gentle Bernard")
    return e


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # Prefix: +aide [commande?] [filtre?]
    @commands.command(name="aide", aliases=["help"], help="Aide avancée avec menu")
    async def aide(self, ctx: commands.Context, commande: Optional[str] = None, filtre: Optional[str] = None):
        f = (filtre or "tous").lower()
        if f not in FILTERS:
            f = "tous"
        entries = _filter_entries(f)

        if commande:
            entry = _find_entry(commande)
            if entry and entry in entries:
                await ctx.send(embed=build_help_embed(entry), view=HelpView(entries))
                return

        await ctx.send(embed=build_welcome_embed(f), view=HelpView(entries))

    # Slash: /aide [commande] [filtre]
    @app_commands.command(name="aide", description="Consulter les informations sur le bot et les commandes")
    @app_commands.describe(
        commande="Nom de la commande (ex: ban, mute, user info)",
        filtre="Filtrer: tous, prefix, slash"
    )
    @app_commands.choices(
        filtre=[
            app_commands.Choice(name="tous", value="tous"),
            app_commands.Choice(name="prefix", value="prefix"),
            app_commands.Choice(name="slash", value="slash"),
        ]
    )
    async def aide_slash(self, interaction: discord.Interaction, commande: Optional[str] = None, filtre: Optional[app_commands.Choice[str]] = None):
        f = (filtre.value if filtre else "tous").lower()
        entries = _filter_entries(f)
        if commande:
            entry = _find_entry(commande)
            if entry and entry in entries:
                await interaction.response.send_message(embed=build_help_embed(entry), view=HelpView(entries))
                return
        await interaction.response.send_message(embed=build_welcome_embed(f), view=HelpView(entries))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
