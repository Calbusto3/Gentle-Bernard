from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv


class Config:
    def __init__(self) -> None:
        # Load .env if present
        load_dotenv(override=False)
        # Support both TOKEN and TOKEN_BOT keys
        self.token: Optional[str] = os.getenv("TOKEN") or os.getenv("TOKEN_BOT")
        # Command prefix (fallback to '+')
        self.prefix: str = os.getenv("PREFIX", "+")
        # Guild allowlist for testing slash commands (optional, comma-separated IDs)
        guild_ids = os.getenv("GUILD_IDS", "").strip()
        if guild_ids:
            self.guild_ids = [int(x) for x in guild_ids.split(",") if x.strip().isdigit()]
        else:
            self.guild_ids = []

        # Role IDs for permissions
        self.staff_role_id: Optional[int] = None
        self.admin_role_id: Optional[int] = None
        sr = os.getenv("STAFF_ROLE_ID", "").strip()
        ar = os.getenv("ADMIN_ROLE_ID", "").strip()
        if sr.isdigit():
            self.staff_role_id = int(sr)
        if ar.isdigit():
            self.admin_role_id = int(ar)

        # Welcome / Goodbye channels with defaults
        welcome_default = "1396111170771091526"
        goodbye_default = "1396111171777462293"
        wc = os.getenv("WELCOME_CHANNEL_ID", welcome_default).strip()
        gc = os.getenv("GOODBYE_CHANNEL_ID", goodbye_default).strip()
        self.welcome_channel_id: Optional[int] = int(wc) if wc.isdigit() else None
        self.goodbye_channel_id: Optional[int] = int(gc) if gc.isdigit() else None


config = Config()
