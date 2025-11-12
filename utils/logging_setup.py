from __future__ import annotations

import logging
from logging import Logger

import colorlog


def setup_logging(level: int = logging.INFO) -> Logger:
    logger = logging.getLogger("cigaming_bot")
    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = colorlog.StreamHandler()
    handler.setLevel(level)

    formatter = colorlog.ColoredFormatter(
        "%(log_color)s[%(levelname)s]%(reset)s %(asctime)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Reduce noise from discord internals; set to INFO or WARNING as desired
    discord_logger = logging.getLogger("discord")
    if not discord_logger.handlers:
        discord_logger.setLevel(logging.WARNING)
        discord_handler = logging.StreamHandler()
        discord_handler.setLevel(logging.WARNING)
        discord_logger.addHandler(discord_handler)

    return logger
