from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional, Tuple

DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdwjm])$", re.IGNORECASE)
# Units: s=seconds, m=minutes, h=hours, d=days, w=weeks, j=jours (days), m (at end) also treated as months≈30d

UNIT_MAP = {
    "s": (1, "secondes"),
    "m": (60, "minutes"),
    "h": (3600, "heures"),
    "d": (86400, "jours"),
    "j": (86400, "jours"),
    "w": (604800, "semaines"),
}

# months approximation to 30 days if explicitly suffixed with 'm' and context implies months.


def parse_duration(token: str) -> Optional[timedelta]:
    token = token.strip()
    m = DURATION_RE.match(token)
    if not m:
        return None
    value = int(m.group("value"))
    unit = m.group("unit").lower()
    if unit == "m":
        # ambiguous: choose minutes by default; months not standard in moderation timeouts
        seconds = value * 60
    else:
        seconds = value * UNIT_MAP[unit][0]
    return timedelta(seconds=seconds)


def humanize_delta(td: timedelta) -> str:
    total = int(td.total_seconds())
    parts = []
    for sec, name in [(604800, "sem"), (86400, "j"), (3600, "h"), (60, "min"), (1, "s")]:
        q, total = divmod(total, sec)
        if q:
            parts.append(f"{q}{name}")
    return " ".join(parts) if parts else "0s"
