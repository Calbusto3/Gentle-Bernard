from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from utils.db import ensure_db
from utils.embeds import success_embed, error_embed
from utils.permissions import is_admin, app_is_admin

# Bitmask permissions
PERM_KICK = 1 << 0
PERM_MUTE = 1 << 1
PERM_LOCK = 1 << 2
PERM_RENAME = 1 << 3
PERM_LIMIT = 1 << 4
PERM_TRANSFER = 1 << 5

ALL_FLAGS = [
    (PERM_KICK, "expulser"),
    (PERM_MUTE, "muter/unmute"),
    (PERM_LOCK, "lock/unlock"),
    (PERM_RENAME, "rename"),
    (PERM_LIMIT, "limiter"),
    (PERM_TRANSFER, "passer la propriété"),
]


def has_flag(mask: int, flag: int) -> bool:
    return (mask & flag) == flag


def toggle_flag(mask: int, flag: int) -> int:
    return mask ^ flag


@dataclass
class HubConfigState:
    guild_id: int
    hub_category_id: Optional[int] = None
    voice_category_id: Optional[int] = None
    name: Optional[str] = None
    perms_mask: int = 0


class CategorySelect(discord.ui.ChannelSelect):
    def __init__(self, state: HubConfigState, target: str = "hub"):
        super().__init__(channel_types=[discord.ChannelType.category], placeholder="Choisissez une catégorie")
        self.state = state
        self.target = target  # 'hub' or 'voice'

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            await interaction.response.send_message("Sélection invalide.", ephemeral=True)
            return
        if self.target == "hub":
            self.state.hub_category_id = self.values[0].id
        else:
            self.state.voice_category_id = self.values[0].id
        await interaction.response.send_message("Catégorie sélectionnée.", ephemeral=True)


class NameModal(discord.ui.Modal, title="Nom du hub vocal"):
    def __init__(self, state: HubConfigState):
        super().__init__()
        self.state = state
        self.name = discord.ui.TextInput(label="Nom du salon vocal hub", max_length=90)
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        self.state.name = str(self.name.value).strip() or None
        if not self.state.name:
            await interaction.response.send_message("Nom invalide.", ephemeral=True)
            return
        await interaction.response.send_message("Nom enregistré.", ephemeral=True)


class PermsToggles(discord.ui.View):
    def __init__(self, state: HubConfigState):
        super().__init__(timeout=300)
        self.state = state
        for flag, label in ALL_FLAGS:
            self.add_item(self._make_button(flag, label))
        self.add_item(self._make_confirm())

    def _label_for(self, flag: int, base: str) -> str:
        return f"{base} ({'ON' if has_flag(self.state.perms_mask, flag) else 'OFF'})"

    def _style_for(self, flag: int) -> discord.ButtonStyle:
        return discord.ButtonStyle.success if has_flag(self.state.perms_mask, flag) else discord.ButtonStyle.secondary

    def _make_button(self, flag: int, label: str) -> discord.ui.Button:
        async def on_click(interaction: discord.Interaction):
            self.state.perms_mask = toggle_flag(self.state.perms_mask, flag)
            # Update the label/style
            btn: discord.ui.Button = interaction.data and next((c for c in self.children if isinstance(c, discord.ui.Button) and c.custom_id == f"perm:{flag}"), None)  # type: ignore[attr-defined]
            # Full refresh
            await interaction.response.edit_message(embed=build_perms_embed(self.state), view=PermsToggles(self.state))

        b = discord.ui.Button(label=self._label_for(flag, label), style=self._style_for(flag), custom_id=f"perm:{flag}")
        b.callback = on_click  # type: ignore[assignment]
        return b

    def _make_confirm(self) -> discord.ui.Button:
        async def on_confirm(interaction: discord.Interaction):
            await interaction.response.send_message("Permissions enregistrées.", ephemeral=True)
        return discord.ui.Button(label="Confirmer", style=discord.ButtonStyle.primary, custom_id="perm:confirm", row=4, disabled=False, callback=on_confirm)  # type: ignore[arg-type]


def build_config_embed(state: HubConfigState) -> discord.Embed:
    e = discord.Embed(title="Configuration du hub temporaire", color=discord.Color.green())
    e.add_field(name="Nom", value=state.name or "(à définir)")
    e.add_field(name="Catégorie du hub", value=f"<#{state.hub_category_id}>" if state.hub_category_id else "(à choisir)")
    e.add_field(name="Catégorie des salons vocaux", value=f"<#{state.voice_category_id}>" if state.voice_category_id else "(à choisir)")
    e.set_footer(text="Gentle Bernard")
    return e


def build_perms_embed(state: HubConfigState) -> discord.Embed:
    lines = []
    for flag, label in ALL_FLAGS:
        lines.append(f"- {label}: {'ON' if has_flag(state.perms_mask, flag) else 'OFF'}")
    e = discord.Embed(title="Permissions du propriétaire", description="\n".join(lines), color=discord.Color.green())
    e.set_footer(text="Gentle Bernard")
    return e


class HubWizard(discord.ui.View):
    pass  # Placeholder: legacy wizard removed in favor of multi-étapes


@dataclass
class Room:
    id: int
    guild_id: int
    hub_id: int
    owner_id: int
    voice_channel_id: int
    text_channel_id: Optional[int]
    control_message_id: Optional[int]
    active: int


class VoiceTemp(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Register persistent control view so buttons survive restarts
        self.bot.add_view(self.ControlPersistentView(self))

    # ---------------- Admin (prefix): +voctemp ----------------
    @commands.command(name="voctemp", help="Créer un hub de salons vocaux temporaires (admin)")
    @is_admin()
    async def voctemp(self, ctx: commands.Context):
        state = HubConfigState(guild_id=ctx.guild.id)  # type: ignore[union-attr]
        await self._run_hub_wizard(ctx, state)

    # ---------------- Admin (prefix): +voctempmodif {id} ----------------
    @commands.command(name="voctempmodif", help="Modifier un hub voc temp: +voctempmodif {id}")
    @is_admin()
    async def voctempmodif(self, ctx: commands.Context, hub_id: int):
        conn = await ensure_db()
        async with conn.execute(
            "SELECT id, guild_id, category_id, target_category_id, hub_channel_id, name, perms_mask FROM voctemp_hubs WHERE id=? AND guild_id=?",
            (hub_id, ctx.guild.id),  # type: ignore[union-attr]
        ) as cur:
            row = await cur.fetchone()
        await conn.close()
        if not row:
            await ctx.send(embed=error_embed("Hub introuvable"))
            return
        _, guild_id, hub_cat, voice_cat, hub_channel_id, name, perms_mask = row
        state = HubConfigState(guild_id=guild_id, hub_category_id=int(hub_cat) if hub_cat else None, voice_category_id=int(voice_cat) if voice_cat else None, name=name, perms_mask=int(perms_mask))
        await self._run_hub_wizard(ctx, state)

    async def _run_hub_wizard(self, ctx: commands.Context, state: HubConfigState):
        author_id = ctx.author.id
        channel = ctx.channel
        # Step 0: Name
        embed = discord.Embed(title="Définir un nom", description="Comment voulez-vous que le hub vocal soit appelé ?", color=discord.Color.green())
        msg = await ctx.send(embed=embed)
        def check_name(m: discord.Message) -> bool:
            return m.author.id == author_id and m.channel.id == channel.id
        try:
            m = await self.bot.wait_for('message', check=check_name, timeout=120)
            state.name = m.content.strip()[:90]
            try:
                await m.delete()
            except Exception:
                pass
        except asyncio.TimeoutError:
            await msg.edit(embed=error_embed("Temps écoulé. Relancez la commande."), view=None)
            return
        # Step 1: Hub category
        proceed_event = asyncio.Event()
        class Step1View(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.add_item(CategorySelect(state, target="hub"))
                self.add_item(self._next())
            def _next(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    if not state.hub_category_id:
                        await inter.response.send_message("Sélectionnez une catégorie.", ephemeral=True)
                        return
                    proceed_event.set()
                    await inter.response.defer()
                b = discord.ui.Button(label="Suivant", style=discord.ButtonStyle.primary)
                b.callback = on_click  # type: ignore[assignment]
                return b
        embed = discord.Embed(title="Sélectionnez la catégorie du hub", description="Choisissez la catégorie où votre hub sera situé.", color=discord.Color.green())
        await msg.edit(embed=embed, view=Step1View())
        try:
            await asyncio.wait_for(proceed_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            await msg.edit(embed=error_embed("Temps écoulé."), view=None)
            return
        # Step 2: Voice category
        proceed_event = asyncio.Event()
        class Step2View(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.add_item(CategorySelect(state, target="voice"))
                self.add_item(self._back())
                self.add_item(self._next())
            def _back(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    nonlocal state
                    # go back to step 1
                    await inter.response.defer()
                    await msg.edit(embed=discord.Embed(title="Sélectionnez la catégorie du hub", description="Choisissez la catégorie où votre hub sera situé.", color=discord.Color.green()), view=Step1View())
                b = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
                b.callback = on_click  # type: ignore[assignment]
                return b
            def _next(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    if not state.voice_category_id:
                        await inter.response.send_message("Sélectionnez une catégorie.", ephemeral=True)
                        return
                    proceed_event.set()
                    await inter.response.defer()
                b = discord.ui.Button(label="Suivant", style=discord.ButtonStyle.primary)
                b.callback = on_click  # type: ignore[assignment]
                return b
        embed = discord.Embed(title="Sélectionnez la catégorie des salons vocaux", description="Choisissez une catégorie où seront créés les salons de discussions.", color=discord.Color.green())
        await msg.edit(embed=embed, view=Step2View())
        try:
            await asyncio.wait_for(proceed_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            await msg.edit(embed=error_embed("Temps écoulé."), view=None)
            return
        # Step 3: Permissions
        proceed_event = asyncio.Event()
        class PermsView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                # build toggle buttons
                for flag, label in ALL_FLAGS:
                    self.add_item(self._make(flag, label))
                self.add_item(self._back())
                self.add_item(self._next())
            def _make(self, flag: int, label: str) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    state.perms_mask = toggle_flag(state.perms_mask, flag)
                    await inter.response.edit_message(embed=build_perms_embed(state), view=PermsView())
                b = discord.ui.Button(label=label + (" (ON)" if has_flag(state.perms_mask, flag) else " (OFF)"), style=discord.ButtonStyle.success if has_flag(state.perms_mask, flag) else discord.ButtonStyle.secondary)
                b.callback = on_click  # type: ignore[assignment]
                return b
            def _back(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    await inter.response.edit_message(embed=discord.Embed(title="Sélectionnez la catégorie des salons vocaux", description="Choisissez une catégorie où seront créés les salons de discussions.", color=discord.Color.green()), view=Step2View())
                b = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
                b.callback = on_click  # type: ignore[assignment]
                return b
            def _next(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    proceed_event.set()
                    await inter.response.defer()
                b = discord.ui.Button(label="Suivant", style=discord.ButtonStyle.primary)
                b.callback = on_click  # type: ignore[assignment]
                return b
        await msg.edit(embed=build_perms_embed(state), view=PermsView())
        try:
            await asyncio.wait_for(proceed_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            await msg.edit(embed=error_embed("Temps écoulé."), view=None)
            return
        # Step 4: Recap + Confirm
        class RecapView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.add_item(self._back())
                self.add_item(self._confirm())
            def _back(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    await inter.response.edit_message(embed=build_perms_embed(state), view=PermsView())
                b = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
                b.callback = on_click  # type: ignore[assignment]
                return b
            def _confirm(self) -> discord.ui.Button:
                async def on_click(inter: discord.Interaction):
                    guild = inter.guild
                    if not guild or not state.hub_category_id or not state.voice_category_id or not state.name:
                        await inter.response.send_message("Configuration incomplète.", ephemeral=True)
                        return
                    hub_cat = guild.get_channel(state.hub_category_id)
                    if not isinstance(hub_cat, discord.CategoryChannel):
                        await inter.response.send_message("Catégorie du hub invalide.", ephemeral=True)
                        return
                    try:
                        hub = await guild.create_voice_channel(state.name, category=hub_cat, reason="Création hub voc temp")
                    except discord.Forbidden:
                        await inter.response.send_message("Permissions insuffisantes pour créer le salon.", ephemeral=True)
                        return
                    conn2 = await ensure_db()
                    await conn2.execute(
                        "INSERT INTO voctemp_hubs(guild_id, category_id, target_category_id, hub_channel_id, name, perms_mask) VALUES(?,?,?,?,?,?)",
                        (guild.id, state.hub_category_id, state.voice_category_id, hub.id, state.name, state.perms_mask),
                    )
                    await conn2.commit()
                    await conn2.close()
                    await inter.response.edit_message(embed=success_embed("Hub créé", f"{hub.mention}"), view=None)
                b = discord.ui.Button(label="Confirmer", style=discord.ButtonStyle.success)
                b.callback = on_click  # type: ignore[assignment]
                return b
        recap = build_config_embed(state)
        recap.title = "Récapitulatif"
        await msg.edit(embed=recap, view=RecapView())

    # ---------------- Helpers DB ----------------
    async def get_perms_mask_for_voice(self, guild_id: int, voice_id: int) -> Optional[int]:
        conn = await ensure_db()
        async with conn.execute("SELECT h.perms_mask FROM voctemp_rooms r JOIN voctemp_hubs h ON r.hub_id=h.id WHERE r.guild_id=? AND r.voice_channel_id=? AND r.active=1", (guild_id, voice_id)) as cur:
            row = await cur.fetchone()
        await conn.close()
        return int(row[0]) if row else None
    async def find_hub_by_channel(self, guild_id: int, channel_id: int) -> Optional[Tuple[int, int, int]]:
        conn = await ensure_db()
        async with conn.execute("SELECT id, target_category_id, perms_mask FROM voctemp_hubs WHERE guild_id=? AND hub_channel_id=?", (guild_id, channel_id)) as cur:
            row = await cur.fetchone()
        await conn.close()
        if not row:
            return None
        return int(row[0]), int(row[1]), int(row[2])

    async def create_room(self, guild: discord.Guild, hub_id: int, category_id: int, owner: discord.Member, base_name: str, perms_mask: int) -> Optional[Room]:
        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            return None
        # Créer salon vocal
        voice = await guild.create_voice_channel(f"Salon de {owner.display_name}", category=category, reason="Salon vocal temporaire")
        # Créer salon texte compagnon
        text = await guild.create_text_channel(f"salon-de-{owner.name}"[:90], category=category, reason="Compagnon salon vocal temp")
        # Envoyer panneau
        panel = await text.send(content=owner.mention, embed=self.build_control_embed(owner, perms_mask, voice), view=self.ControlPersistentView(self, owner_id=owner.id, perms_mask=perms_mask, voice_id=voice.id), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        conn = await ensure_db()
        await conn.execute(
            "INSERT INTO voctemp_rooms(guild_id, hub_id, owner_id, voice_channel_id, text_channel_id, control_message_id, active) VALUES(?,?,?,?,?,?,1)",
            (guild.id, hub_id, owner.id, voice.id, text.id, panel.id),
        )
        await conn.commit()
        await conn.close()
        # Déplacer le membre
        try:
            await owner.move_to(voice, reason="Création salon vocal temporaire")
        except Exception:
            pass
        return Room(id=0, guild_id=guild.id, hub_id=hub_id, owner_id=owner.id, voice_channel_id=voice.id, text_channel_id=text.id, control_message_id=panel.id, active=1)

    def build_control_embed(self, owner: discord.Member, perms_mask: int, voice: discord.VoiceChannel) -> discord.Embed:
        lines = []
        for flag, label in ALL_FLAGS:
            allowed = has_flag(perms_mask, flag)
            suffix = "" if allowed else " (non autorisé)"
            lines.append(f"- {label}{suffix}")
        e = discord.Embed(title=f"Salon vocal de {owner.display_name}", description="\n".join(lines), color=discord.Color.green())
        e.add_field(name="Salon vocal", value=f"{voice.mention}")
        e.add_field(name="Actions", value="Utilisez les boutons ci-dessous.", inline=False)
        e.set_footer(text="Gentle Bernard")
        return e

    class ControlPersistentView(discord.ui.View):
        def __init__(self, outer: 'VoiceTemp', owner_id: Optional[int] = None, perms_mask: Optional[int] = None, voice_id: Optional[int] = None):
            super().__init__(timeout=None)
            self.outer = outer
            self.owner_id = owner_id
            self.perms_mask = perms_mask
            self.voice_id = voice_id
            # When instantiated without specific ids (during startup), buttons still exist to capture custom_ids
            # Buttons will parse voice_id from custom_id

        async def _ensure_owner(self, inter: discord.Interaction, voice_id: int) -> Optional[discord.Member]:
            if not inter.guild:
                await inter.response.send_message("Contexte invalide.", ephemeral=True)
                return None
            member = inter.guild.get_member(inter.user.id)
            if not member:
                await inter.response.send_message("Membre introuvable.", ephemeral=True)
                return None
            conn = await ensure_db()
            async with conn.execute("SELECT owner_id FROM voctemp_rooms WHERE guild_id=? AND voice_channel_id=? AND active=1", (inter.guild.id, voice_id)) as cur:
                row = await cur.fetchone()
            await conn.close()
            if not row or int(row[0]) != member.id:
                await inter.response.send_message("Seul le propriétaire peut utiliser ce panneau.", ephemeral=True)
                return None
            # Require the owner to be currently connected in the target voice channel
            if not member.voice or not member.voice.channel or member.voice.channel.id != voice_id:
                await inter.response.send_message("Vous devez être dans votre salon vocal pour utiliser ce panneau.", ephemeral=True)
                return None
            return member

        def _voice_id_from_message(self, inter: discord.Interaction) -> int:
            try:
                msg = inter.message
                if not msg or not msg.embeds:
                    return 0
                emb = msg.embeds[0]
                for f in emb.fields:
                    if f.name.lower() == "salon vocal":
                        # value like <#123456789>
                        digits = "".join(ch for ch in f.value if ch.isdigit())
                        return int(digits) if digits else 0
            except Exception:
                return 0
            return 0

        def _get_ids(self, custom_id: str, inter: Optional[discord.Interaction] = None) -> Tuple[str, int]:
            parts = custom_id.split(":")
            action = parts[1] if len(parts) > 1 else ""
            vid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else (self.voice_id or 0)
            if vid == 0 and inter is not None:
                vid = self._voice_id_from_message(inter)
            return action, vid

        @discord.ui.button(label="Renommer", style=discord.ButtonStyle.primary, custom_id="voctemp:rename:0")
        async def btn_rename(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'rename' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            # Enforce mask
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_RENAME):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            class RenameModal(discord.ui.Modal, title="Renommer le salon"):
                def __init__(self):
                    super().__init__()
                    self.name = discord.ui.TextInput(label="Nouveau nom", max_length=90)
                    self.add_item(self.name)
                async def on_submit(self, i: discord.Interaction):
                    owner = await self_outer._ensure_owner(i, vid)
                    if not owner or not i.guild:
                        return
                    vc = i.guild.get_channel(vid)
                    if isinstance(vc, discord.VoiceChannel):
                        try:
                            await vc.edit(name=str(self.name.value)[:90])
                            await i.response.send_message("Nom mis à jour.", ephemeral=True)
                        except Exception:
                            await i.response.send_message("Impossible de renommer.", ephemeral=True)
            self_outer = self
            await inter.response.send_modal(RenameModal())

        @discord.ui.button(label="Limiter", style=discord.ButtonStyle.secondary, custom_id="voctemp:limit:0")
        async def btn_limit(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'limit' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_LIMIT):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            class LimitModal(discord.ui.Modal, title="Limiter le salon"):
                def __init__(self):
                    super().__init__()
                    self.val = discord.ui.TextInput(label="Limite (0 pour illimité)", max_length=3)
                    self.add_item(self.val)
                async def on_submit(self, i: discord.Interaction):
                    owner = await self_outer._ensure_owner(i, vid)
                    if not owner or not i.guild:
                        return
                    try:
                        limit = max(0, min(99, int(str(self.val.value))))
                    except Exception:
                        await i.response.send_message("Valeur invalide.", ephemeral=True)
                        return
                    vc = i.guild.get_channel(vid)
                    if isinstance(vc, discord.VoiceChannel):
                        try:
                            await vc.edit(user_limit=limit)
                            await i.response.send_message("Limite mise à jour.", ephemeral=True)
                        except Exception:
                            await i.response.send_message("Impossible de mettre à jour la limite.", ephemeral=True)
            self_outer = self
            await inter.response.send_modal(LimitModal())

        @discord.ui.button(label="Lock/Unlock", style=discord.ButtonStyle.secondary, custom_id="voctemp:lock:0")
        async def btn_lock(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'lock' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_LOCK):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            owner = await self._ensure_owner(inter, vid)
            if not owner or not inter.guild:
                return
            vc = inter.guild.get_channel(vid)
            if not isinstance(vc, discord.VoiceChannel):
                await inter.response.send_message("Salon introuvable.", ephemeral=True)
                return
            everyone = inter.guild.default_role
            ow = vc.overwrites_for(everyone)
            locked = ow.connect is False
            ow.connect = None if locked else False
            try:
                await vc.set_permissions(everyone, overwrite=ow)
                await inter.response.send_message("Salon verrouillé" if not locked else "Salon déverrouillé", ephemeral=True)
            except Exception:
                await inter.response.send_message("Action impossible.", ephemeral=True)

        @discord.ui.button(label="Passer la propriété", style=discord.ButtonStyle.success, custom_id="voctemp:transfer:0")
        async def btn_transfer(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'transfer' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_TRANSFER):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            owner = await self._ensure_owner(inter, vid)
            if not owner or not inter.guild:
                return
            vc = inter.guild.get_channel(vid)
            if not isinstance(vc, discord.VoiceChannel):
                await inter.response.send_message("Salon introuvable.", ephemeral=True)
                return
            candidates = [m for m in vc.members if m.id != owner.id]
            if not candidates:
                await inter.response.send_message("Aucun candidat dans le salon.", ephemeral=True)
                return
            new_owner = candidates[0]
            conn = await ensure_db()
            await conn.execute("UPDATE voctemp_rooms SET owner_id=? WHERE guild_id=? AND voice_channel_id=? AND active=1", (new_owner.id, inter.guild.id, vid))
            await conn.commit()
            await conn.close()
            await inter.response.send_message(f"Propriété transférée à {new_owner.mention}", ephemeral=True)

        # ----- Actions sur membres: Kick / Mute / Unmute -----
        class _SelectMemberView(discord.ui.View):
            def __init__(self, outer_view: 'VoiceTemp.ControlPersistentView', action: str, voice_id: int):
                super().__init__(timeout=60)
                self.outer_view = outer_view
                self.action = action
                self.voice_id = voice_id
                self.add_item(self._make_select())

            def _make_select(self) -> discord.ui.UserSelect:
                select = discord.ui.UserSelect(min_values=1, max_values=1)
                async def on_select(inter: discord.Interaction):
                    user = select.values[0]
                    if not inter.guild:
                        await inter.response.send_message("Contexte invalide.", ephemeral=True)
                        return
                    member = inter.guild.get_member(user.id)
                    owner = await self.outer_view._ensure_owner(inter, self.voice_id)
                    if not owner:
                        return
                    vc = inter.guild.get_channel(self.voice_id)
                    if not isinstance(vc, discord.VoiceChannel) or member not in vc.members:
                        await inter.response.send_message("Le membre n'est pas dans votre salon", ephemeral=True)
                        return
                    try:
                        if self.action == 'kick':
                            await member.move_to(None, reason="Expulsion du salon vocal temp")
                        elif self.action == 'mute':
                            await member.edit(mute=True, reason="Mute salon vocal temp")
                        elif self.action == 'unmute':
                            await member.edit(mute=False, reason="Unmute salon vocal temp")
                        await inter.response.edit_message(view=self.outer_view)
                    except Exception:
                        await inter.response.send_message("Action impossible.", ephemeral=True)
                select.callback = on_select  # type: ignore[assignment]
                return select

        @discord.ui.button(label="Expulser", style=discord.ButtonStyle.danger, custom_id="voctemp:kick:0")
        async def btn_kick(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'kick' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_KICK):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            await inter.response.edit_message(view=_SelectMemberView(self, 'kick', vid))

        @discord.ui.button(label="Mute", style=discord.ButtonStyle.secondary, custom_id="voctemp:mute:0")
        async def btn_mute(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'mute' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_MUTE):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            await inter.response.edit_message(view=_SelectMemberView(self, 'mute', vid))

        @discord.ui.button(label="Unmute", style=discord.ButtonStyle.secondary, custom_id="voctemp:unmute:0")
        async def btn_unmute(self, inter: discord.Interaction, btn: discord.ui.Button):  # type: ignore[override]
            action, vid = self._get_ids(inter.data.get('custom_id', ''), inter)  # type: ignore[attr-defined]
            if action != 'unmute' or vid == 0:
                await inter.response.send_message("Panneau non initialisé.", ephemeral=True)
                return
            mask = await self.outer.get_perms_mask_for_voice(inter.guild.id, vid) if inter.guild else None
            if mask is None or not has_flag(mask, PERM_MUTE):
                await inter.response.send_message("Action non autorisée.", ephemeral=True)
                return
            await inter.response.edit_message(view=_SelectMemberView(self, 'unmute', vid))

    def build_control_view(self, owner_id: int, perms_mask: int, voice_id: int) -> discord.ui.View:
        # Backward compat if needed elsewhere, but we'll primarily use ControlPersistentView
        return self.ControlPersistentView(self, owner_id=owner_id, perms_mask=perms_mask, voice_id=voice_id)

        async def ensure_owner(inter: discord.Interaction) -> Optional[discord.Member]:
            if not inter.guild:
                await inter.response.send_message("Contexte invalide.", ephemeral=True)
                return None
            member = inter.guild.get_member(inter.user.id)
            if not member:
                await inter.response.send_message("Membre introuvable.", ephemeral=True)
                return None
            # Vérifier propriétaire
            conn = await ensure_db()
            async with conn.execute("SELECT owner_id FROM voctemp_rooms WHERE guild_id=? AND voice_channel_id=? AND active=1", (inter.guild.id, voice_id)) as cur:
                row = await cur.fetchone()
            await conn.close()
            if not row or int(row[0]) != member.id:
                await inter.response.send_message("Seul le propriétaire peut utiliser ce panneau.", ephemeral=True)
                return None
            return member

        # RENAME
        if has_flag(perms_mask, PERM_RENAME):
            class RenameModal(discord.ui.Modal, title="Renommer le salon"):
                def __init__(self):
                    super().__init__()
                    self.name = discord.ui.TextInput(label="Nouveau nom", max_length=90)
                    self.add_item(self.name)
                async def on_submit(self, inter: discord.Interaction):
                    member = await ensure_owner(inter)
                    if not member or not inter.guild:
                        return
                    voice = inter.guild.get_channel(voice_id)
                    if isinstance(voice, discord.VoiceChannel):
                        try:
                            await voice.edit(name=str(self.name.value)[:90])
                            await inter.response.send_message("Nom mis à jour.", ephemeral=True)
                        except Exception:
                            await inter.response.send_message("Impossible de renommer.", ephemeral=True)
            async def on_rename(inter: discord.Interaction):
                await inter.response.send_modal(RenameModal())
            btn = discord.ui.Button(label="Renommer", style=discord.ButtonStyle.primary, custom_id=f"voctemp:rename:{voice_id}")
            btn.callback = on_rename  # type: ignore[assignment]
            view.add_item(btn)

        # LIMIT
        if has_flag(perms_mask, PERM_LIMIT):
            class LimitModal(discord.ui.Modal, title="Limiter le salon"):
                def __init__(self):
                    super().__init__()
                    self.val = discord.ui.TextInput(label="Limite (0 pour illimité)", max_length=3)
                    self.add_item(self.val)
                async def on_submit(self, inter: discord.Interaction):
                    member = await ensure_owner(inter)
                    if not member or not inter.guild:
                        return
                    try:
                        limit = max(0, min(99, int(str(self.val.value))))
                    except Exception:
                        await inter.response.send_message("Valeur invalide.", ephemeral=True)
                        return
                    voice = inter.guild.get_channel(voice_id)
                    if isinstance(voice, discord.VoiceChannel):
                        try:
                            await voice.edit(user_limit=limit)
                            await inter.response.send_message("Limite mise à jour.", ephemeral=True)
                        except Exception:
                            await inter.response.send_message("Impossible de mettre à jour la limite.", ephemeral=True)
            async def on_limit(inter: discord.Interaction):
                await inter.response.send_modal(LimitModal())
            btn = discord.ui.Button(label="Limiter", style=discord.ButtonStyle.secondary, custom_id=f"voctemp:limit:{voice_id}")
            btn.callback = on_limit  # type: ignore[assignment]
            view.add_item(btn)

        # LOCK/UNLOCK
        if has_flag(perms_mask, PERM_LOCK):
            async def on_lock_toggle(inter: discord.Interaction):
                member = await ensure_owner(inter)
                if not member or not inter.guild:
                    return
                voice = inter.guild.get_channel(voice_id)
                if not isinstance(voice, discord.VoiceChannel):
                    await inter.response.send_message("Salon introuvable.", ephemeral=True)
                    return
                everyone = inter.guild.default_role
                ow = voice.overwrites_for(everyone)
                locked = ow.connect is False
                ow.connect = None if locked else False
                try:
                    await voice.set_permissions(everyone, overwrite=ow)
                    await inter.response.send_message("Salon verrouillé" if not locked else "Salon déverrouillé", ephemeral=True)
                except Exception:
                    await inter.response.send_message("Action impossible.", ephemeral=True)
            btn = discord.ui.Button(label="Lock/Unlock", style=discord.ButtonStyle.secondary, custom_id=f"voctemp:lock:{voice_id}")
            btn.callback = on_lock_toggle  # type: ignore[assignment]
            view.add_item(btn)

        # TRANSFER
        if has_flag(perms_mask, PERM_TRANSFER):
            async def on_transfer(inter: discord.Interaction):
                member = await ensure_owner(inter)
                if not member or not inter.guild:
                    return
                voice = inter.guild.get_channel(voice_id)
                if not isinstance(voice, discord.VoiceChannel):
                    await inter.response.send_message("Salon introuvable.", ephemeral=True)
                    return
                # Simple transfert au dernier membre (hors owner) si présent
                candidates = [m for m in voice.members if m.id != member.id]
                if not candidates:
                    await inter.response.send_message("Aucun candidat dans le salon.", ephemeral=True)
                    return
                new_owner = candidates[0]
                conn = await ensure_db()
                await conn.execute("UPDATE voctemp_rooms SET owner_id=? WHERE guild_id=? AND voice_channel_id=? AND active=1", (new_owner.id, inter.guild.id, voice_id))
                await conn.commit()
                await conn.close()
                await inter.response.send_message(f"Propriété transférée à {new_owner.mention}", ephemeral=True)
            btn = discord.ui.Button(label="Passer la propriété", style=discord.ButtonStyle.success, custom_id=f"voctemp:transfer:{voice_id}")
            btn.callback = on_transfer  # type: ignore[assignment]
            view.add_item(btn)

        return view

    # ---------------- Voice events ----------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Création: si rejoint un hub
        if after and after.channel and isinstance(after.channel, discord.VoiceChannel):
            hub = await self.find_hub_by_channel(member.guild.id, after.channel.id)
            if hub:
                hub_id, category_id, perms_mask = hub
                # Créer room
                await self.create_room(member.guild, hub_id, category_id, member, after.channel.name, perms_mask)
                return
        # Suppression: si quitte un salon temporaire et qu'il devient vide
        if before and before.channel and isinstance(before.channel, discord.VoiceChannel):
            voice = before.channel
            # Est-ce un salon temp ?
            conn = await ensure_db()
            async with conn.execute("SELECT id, text_channel_id FROM voctemp_rooms WHERE guild_id=? AND voice_channel_id=? AND active=1", (member.guild.id, voice.id)) as cur:
                row = await cur.fetchone()
            if row and len(voice.members) == 0:
                room_id, text_id = row
                # Supprimer tout
                try:
                    if text_id:
                        ch = member.guild.get_channel(int(text_id))
                        if isinstance(ch, discord.TextChannel):
                            await ch.delete(reason="Salon vocal temp vide")
                    await voice.delete(reason="Salon vocal temp vide")
                except Exception:
                    pass
                await conn.execute("UPDATE voctemp_rooms SET active=0 WHERE id=?", (room_id,))
                await conn.commit()
            await conn.close()



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceTemp(bot))
