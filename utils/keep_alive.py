from __future__ import annotations

import os
from typing import Optional

from aiohttp import web


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def _root(request: web.Request) -> web.Response:
    return web.Response(text="CIGaming Bot alive", content_type="text/plain")


async def start_keep_alive() -> web.AppRunner:
    """Start a minimal HTTP server for uptime pings.

    Env variables:
      - KEEP_ALIVE_HOST (default: 0.0.0.0)
      - KEEP_ALIVE_PORT (default: 8080)
    """
    host = os.getenv("KEEP_ALIVE_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("KEEP_ALIVE_PORT", "8080"))
    except ValueError:
        port = 8080

    app = web.Application()
    app.add_routes([
        web.get("/", _root),
        web.get("/health", _health),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner


async def stop_keep_alive(runner: Optional[web.AppRunner]) -> None:
    if runner is None:
        return
    try:
        await runner.cleanup()
    except Exception:
        pass
