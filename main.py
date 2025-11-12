from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

from utils.config import config
from utils.logging_setup import setup_logging
from utils.keep_alive import start_keep_alive, stop_keep_alive


COGS_FOLDER = Path(__file__).parent / "cogs"


class CIGamingBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.members = True  # For member info and autocomplete
        intents.voice_states = True  # For voice temp system
        intents.message_content = True  # Requires privileged intent enabled in the Developer Portal

        super().__init__(command_prefix=config.prefix, intents=intents, help_command=None)
        self.logger = setup_logging(logging.INFO)

    async def setup_hook(self) -> None:
        # Dynamically load all cogs from the cogs directory
        if COGS_FOLDER.exists():
            for file in COGS_FOLDER.glob("*.py"):
                if file.name.startswith("__"):
                    continue
                ext = f"cogs.{file.stem}"
                try:
                    await self.load_extension(ext)
                    self.logger.info(f"Extension chargée: {ext}")
                except Exception as e:
                    self.logger.error(f"Impossible de charger l'extension {ext}: {e}")

        # Sync slash commands
        try:
            if getattr(config, "guild_ids", []):
                guilds = [discord.Object(id=g) for g in config.guild_ids]
                for g in guilds:
                    await self.tree.sync(guild=g)
                self.logger.info(f"Slash commands synchronisés sur {len(guilds)} guilde(s)")
            else:
                await self.tree.sync()
                self.logger.info("Slash commands synchronisés globalement")
        except Exception as e:
            self.logger.error(f"Erreur de synchronisation des commandes: {e}")

    async def on_ready(self) -> None:
        self.logger.info(f"Connecté en tant que {self.user} (ID: {self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Une grenouille presque verte"))


async def main() -> None:
    token = config.token
    if not token:
        raise RuntimeError("Aucun token trouvé. Définissez TOKEN ou TOKEN_BOT dans le fichier .env")

    bot = CIGamingBot()

    runner = None
    try:
        runner = await start_keep_alive()
    except Exception as e:
        # Le bot peut démarrer même si le keep-alive échoue
        logging.getLogger(__name__).warning(f"Keep-alive non démarré: {e}")

    async with bot:
        try:
            await bot.start(token)
        finally:
            await stop_keep_alive(runner)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
