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
        # Accept lowercase aliases too
        sr = (os.getenv("STAFF_ROLE_ID") or os.getenv("staff_role_id") or "").strip()
        ar = (os.getenv("ADMIN_ROLE_ID") or os.getenv("admin_role_id") or "").strip()
        if sr.isdigit():
            self.staff_role_id = int(sr)
        if ar.isdigit():
            self.admin_role_id = int(ar)

        # Welcome / Goodbye channels with defaults
        welcome_default = "1396111170771091526"
        goodbye_default = "1396111171777462293"
        wc = os.getenv("WELCOME_CHANNEL_ID", welcome_default).strip()
        # Accept BYE_CHANNEL_ID as alias
        gc = (os.getenv("GOODBYE_CHANNEL_ID") or os.getenv("BYE_CHANNEL_ID") or goodbye_default).strip()
        self.welcome_channel_id: Optional[int] = int(wc) if wc.isdigit() else None
        self.goodbye_channel_id: Optional[int] = int(gc) if gc.isdigit() else None

        # Confession logs channel
        # Accept CONFESSION_SALON_ID as alias
        cl = (os.getenv("CONFESSION_LOGS_ID") or os.getenv("CONFESSION_SALON_ID") or "").strip()
        self.confession_logs_id: Optional[int] = int(cl) if cl.isdigit() else None

        # Optional owner id
        owner = (os.getenv("BOT_OWNER_ID") or os.getenv("OWNER_ID") or "").strip()
        self.owner_id: Optional[int] = int(owner) if owner.isdigit() else None


config = Config()
